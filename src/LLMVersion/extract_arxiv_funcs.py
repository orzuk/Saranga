#!/usr/bin/env python3
"""
extract_arxiv_funcs.py

Core library for fetching arXiv papers and metadata.
Provides functions for:
- Listing/filtering arXiv IDs by date, category, author, title
- Fetching metadata from local HDF5 index or remote API
- Downloading LaTeX source, PDF, and HTML
- Local-first caching with remote fallback
"""


import subprocess

import os
import re
import json
import requests
import argparse
import sys
import time
import datetime
import tarfile
import io
import gzip
import xml.etree.ElementTree as ET
import urllib.request as urlrequest
import urllib.parse   as urlparse
from urllib.error import HTTPError
from collections import Counter
from urllib.parse import urlencode
from email.utils import parsedate_to_datetime
from typing import Iterator, Dict, List, Union, Optional, Any, Tuple
from requests.exceptions import HTTPError, RequestException
from pathlib import Path


import shutil
from pathlib import Path




import pandas as pd
import tables

from config import *
import pickle
import h5py


ARXIV_ID_RE = re.compile(r"^(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?$")
URL_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")

def normalize_arxiv_id(s: str) -> str:
    """
    Accepts:
        - '2101.12345'
        - 'arXiv:2101.12345'
        - 'https://arxiv.org/abs/2101.12345v2'
    Returns base ID: '2101.12345'
    """
    s = s.strip()
    m = ARXIV_ID_RE.match(s)
    if m:
        return m.group(1)

    m = URL_ID_RE.search(s)
    if m:
        return m.group(1)

    raise ValueError(f"Cannot parse arXiv ID from: {s}")


def meta_data_full_to_hdf5(
    src_path:    str = ARXIV_META_DATA,
    hdf5_path:   str = ARXIV_META_DATA_HDF5,
    overwrite:   bool  = False,
    verbose:     bool  = False,
    chunk_size:  int   = 100_000
):
    """
    Read 'arxiv-metadata-oai-snapshot.json' (NDJSON) once, and build an HDF5 file
    with these datasets (all variable-length UTF-8 except 'offset' and fixed-length 'created'):
      - base_id    : variable-length UTF-8 strings
      - offset     : int64
      - categories : variable-length UTF-8 strings
      - created    : fixed-length ASCII "YYYY-MM-DD"
      - authors    : variable-length UTF-8 strings
      - title      : variable-length UTF-8 strings

    This version uses a loop over column definitions instead of manual repetition.
    """


    if verbose:
        print("h5 File exists? ", os.path.exists(hdf5_path), " ; overwrite? ", overwrite)
    if not overwrite and os.path.exists(hdf5_path):
        if verbose:
            print(f"[skip] '{hdf5_path}' already exists.")
        return

    if overwrite and os.path.exists(hdf5_path):
        if verbose:
            print(f"[build] Removing existing '{hdf5_path}' …")
        os.remove(hdf5_path)

    if verbose:
        print(f"[build] Scanning '{src_path}' → writing '{hdf5_path}' …")

    with h5py.File(hdf5_path, "w") as h5f:
        # Define dtypes for each column
        vlen_utf8 = h5py.string_dtype(encoding="utf-8")
        fixed_date = h5py.string_dtype(encoding="ascii", length=10)

        column_specs = {
            "base_id":    dict(dtype=vlen_utf8),
            "offset":     dict(dtype="int64"),
            "categories": dict(dtype=vlen_utf8),
            "created":    dict(dtype=fixed_date),
            "authors":    dict(dtype=vlen_utf8),
            "title":      dict(dtype=vlen_utf8),
        }

        # Create empty, resizable datasets for each column
        dsets = {}
        for col, spec in column_specs.items():
            dsets[col] = h5f.create_dataset(
                col,
                shape=(0,),
                maxshape=(None,),
                dtype=spec["dtype"],
                chunks=True
            )

        # Buffers for chunked writing
        bufs = {col: [] for col in column_specs}

        total = 0
        with open(src_path, "r", encoding="utf-8") as fin:
            while True:
                offset_byte = fin.tell()
                line = fin.readline()
                if not line:
                    break

                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                base_id = rec.get("id")
                if not base_id:
                    continue

                # created_iso as bytes
                created_full = rec.get("versions", [{}])[0].get("created", "")
                try:
                    dt = parsedate_to_datetime(created_full)
                    created_iso = dt.date().isoformat().encode("ascii")
                except Exception:
                    created_iso = b""

                cats    = rec.get("categories", "")
                authors = rec.get("authors", "")
                title   = rec.get("title", "")

                # Fill buffers
                bufs["base_id"].append(base_id)
                bufs["offset"].append(offset_byte)
                bufs["categories"].append(cats)
                bufs["created"].append(created_iso)
                bufs["authors"].append(authors)
                bufs["title"].append(title)

                total += 1
                if total % chunk_size == 0:
                    start = dsets["base_id"].shape[0]
                    end = start + chunk_size
                    for col in column_specs:
                        dset = dsets[col]
                        dset.resize((end,))
                        dset[start:end] = bufs[col]
                        bufs[col].clear()
                    if verbose:
                        print(f"[build] Appended {end:,} records…")

        # Flush any remaining rows
        if bufs["base_id"]:
            n_rem = len(bufs["base_id"])
            start = dsets["base_id"].shape[0]
            end = start + n_rem
            for col in column_specs:
                dset = dsets[col]
                dset.resize((end,))
                dset[start:end] = bufs[col]
            if verbose:
                print(f"[build] Appended final {n_rem:,} records, total {end:,}")

    if verbose:
        print(f"[build] Done. HDF5 written: '{hdf5_path}' with {total:,} rows.")


def meta_data_full_to_compact(src_path=ARXIV_META_DATA,
                              dest_path=ARXIV_META_DATA_COMPACT,
                              overwrite = False, verbose=False):
    """
    Read the full 'arxiv-metadata-oai-snapshot.json' (NDJSON) and produce ONE pickle file
    containing two dictionaries under a single top‐level object:
      {
        "compact": { base_id: { "categories":…, "created":…, "authors":…, "title":… }, … },
        "offsets": { base_id: byte_offset, … }
      }

    Parameters
    ----------
    src_path : str
        Path to the 4 GB NDJSON (one JSON object per line).
    combined_dest : str
        Where to write the combined pickle.  Example: "arxiv-combined.pkl".
    overwrite : bool
        If False and combined_dest already exists, do nothing.
    verbose : bool
        If True, print progress every 100 000 records.

    After running, you will have a single pickle file that contains:
      - combined["compact"]  → trimmed metadata for each base_id
      - combined["offsets"]  → byte‐offset for each base_id in the original JSONL

    Use `load_combined_index(combined_dest)` to get those two dicts back in memory.
    """
    if not overwrite and os.path.exists(dest_path):
        if verbose:
            print(f"[skip] '{dest_path}' already exists.")
        return

    if verbose:
        print(f"[build] Scanning '{src_path}' to build combined index…")

    compact_index: Dict[str, Dict[str, str]] = {}
    offsets:        Dict[str, int]          = {}

    with open(src_path, "r", encoding="utf-8") as fin:
        while True:
            offset = fin.tell()
            line = fin.readline()
            if not line:
                break

            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            base_id = rec.get("id")
            if not base_id:
                continue

            # Record the byte offset once
            if base_id not in offsets:
                offsets[base_id] = offset

            # Parse version-1 creation date into "YYYY-MM-DD"
            created_full = rec.get("versions", [{}])[0].get("created", "")
            try:
                dt = parsedate_to_datetime(created_full)
                created_iso = dt.date().isoformat()
            except Exception:
                created_iso = ""

            # Extract trimmed metadata
            cats    = rec.get("categories", "")
            authors = rec.get("authors", "")
            title   = rec.get("title", "")

            # Only store compact metadata the first time we see base_id
            if base_id not in compact_index:
                compact_index[base_id] = {
                    "categories": cats,
                    "created":    created_iso,
                    "authors":    authors,
                    "title":      title
                }

            # Progress every 100 000 records
            if verbose and len(offsets) % 100_000 == 0:
                print(f"[build] Indexed {len(offsets):,} records so far…")

    # Write out one pickle that holds both dicts
    combined = {
        "compact": compact_index,
        "offsets": offsets
    }
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        pickle.dump(combined, f, protocol=pickle.HIGHEST_PROTOCOL)

    if verbose:
        print(f"[build] Wrote combined pickle with {len(compact_index):,} entries to '{dest_path}'")



def load_meta_data_hdf5(
    hdf5_path: str = ARXIV_META_DATA_HDF5,
    cols:      Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Load selected columns from the HDF5 compact index created by `meta_data_full_to_hdf5`.

    Parameters
    ----------
    hdf5_path : str
        Path to the HDF5 file (e.g. "arxiv-compact.h5").
    cols : list of str, optional
        Which columns to read. Valid names are:
          "offset", "categories", "created", "authors", "title"
        (We always implicitly load "base_id" so that we can key the dict by it.)
        If None, all five of those columns are loaded.

    Returns
    -------
    A dict mapping each base_id → dict of the requested columns. For example:
      {
        "2309.00543": { "offset": 123456, "categories": "cs.LG cs.AI", … },
        "2309.00176": { … },
        …
      }
    """
    if not os.path.exists(hdf5_path):
        raise FileNotFoundError(f"No such file: {hdf5_path}")

    # The only valid column names (aside from base_id):
    valid_cols = {"offset", "categories", "created", "authors", "title"}
    if cols is None:
        cols_to_load = list(valid_cols)
    else:
        missing = set(cols) - valid_cols
        if missing:
            raise ValueError(f"Unknown columns requested: {missing}. Valid: {valid_cols}")
        cols_to_load = list(cols)

    # We always need "base_id" internally so that we can key the results dictionary
    # by base_id.
    to_read = ["base_id"] + cols_to_load

    result: Dict[str, Dict[str, Any]] = {}

    with h5py.File(hdf5_path, "r") as h5f:
        # Determine how many rows / total entries exist
        total = h5f["base_id"].shape[0]

        # Read each requested dataset into memory
        data = {}
        for key in to_read:
            data[key] = h5f[key][()]

        # Now build the nested dict: base_id → { col: value, … }
        for i in range(total):
            base_id_bytes = data["base_id"][i]
            # decode bytes → str (UTF-8)
            base_id = base_id_bytes.decode("utf-8")

            entry: Dict[str, Any] = {}
            for col in cols_to_load:
                val = data[col][i]
                # If the dataset is stored as bytes (e.g. "categories", "authors", "title",
                # or the fixed-length ASCII "created"), decode to str:
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode("utf-8")
                    except:
                        val = val.decode("ascii", errors="ignore")
                entry[col] = val

            result[base_id] = entry

    return result


def iter_meta_data_hdf5(
    hdf5_path: str = ARXIV_META_DATA_HDF5,
    cols: Optional[List[str]] = None,
    chunk_size: int = 10_000
) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """
    Memory-efficient generator that yields (base_id, record_dict) tuples.

    Reads HDF5 data in chunks to avoid loading entire dataset into memory.
    Useful for processing 2M+ records without memory issues.

    Parameters
    ----------
    hdf5_path : str
        Path to the HDF5 file.
    cols : list of str, optional
        Which columns to read. If None, loads all columns.
    chunk_size : int
        Number of records to load per chunk (default 10,000).

    Yields
    ------
    (base_id, record_dict) : tuple
        Each record as a (key, value) pair.
    """
    if not os.path.exists(hdf5_path):
        raise FileNotFoundError(f"No such file: {hdf5_path}")

    valid_cols = {"offset", "categories", "created", "authors", "title"}
    if cols is None:
        cols_to_load = list(valid_cols)
    else:
        cols_to_load = [c for c in cols if c in valid_cols]

    with h5py.File(hdf5_path, "r") as h5f:
        total = h5f["base_id"].shape[0]

        for start in range(0, total, chunk_size):
            end = min(start + chunk_size, total)

            # Read chunk of base_ids
            base_ids_chunk = h5f["base_id"][start:end]

            # Read chunks of requested columns
            col_chunks = {}
            for col in cols_to_load:
                col_chunks[col] = h5f[col][start:end]

            # Yield records one at a time
            for i in range(end - start):
                base_id = base_ids_chunk[i]
                if isinstance(base_id, bytes):
                    base_id = base_id.decode("utf-8")

                entry = {}
                for col in cols_to_load:
                    val = col_chunks[col][i]
                    if isinstance(val, (bytes, bytearray)):
                        try:
                            val = val.decode("utf-8")
                        except:
                            val = val.decode("ascii", errors="ignore")
                    entry[col] = val

                yield base_id, entry


def load_meta_data_hdf5_by_ids(
    base_ids: List[str],
    hdf5_path: str = ARXIV_META_DATA_HDF5,
    cols: Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Load metadata for specific base_ids only, using index lookup.

    Much more efficient than load_meta_data_hdf5() when you only need
    a small subset of the 2M+ records.

    Parameters
    ----------
    base_ids : list of str
        The specific arXiv IDs to load.
    hdf5_path : str
        Path to the HDF5 file.
    cols : list of str, optional
        Which columns to read. If None, loads all columns.

    Returns
    -------
    Dict mapping base_id -> record dict (only for IDs that were found).
    """
    if not os.path.exists(hdf5_path):
        raise FileNotFoundError(f"No such file: {hdf5_path}")

    if not base_ids:
        return {}

    valid_cols = {"offset", "categories", "created", "authors", "title"}
    if cols is None:
        cols_to_load = list(valid_cols)
    else:
        cols_to_load = [c for c in cols if c in valid_cols]

    wanted = set(base_ids)
    result: Dict[str, Dict[str, Any]] = {}

    # Stream through in chunks to find matching IDs
    for base_id, entry in iter_meta_data_hdf5(hdf5_path, cols=cols_to_load):
        if base_id in wanted:
            result[base_id] = entry
            wanted.discard(base_id)
            # Early exit if we found all requested IDs
            if not wanted:
                break

    return result


def load_meta_data_compact(
        dest_path=ARXIV_META_DATA_COMPACT  # type: str
) -> Dict[str, Dict[str, str]]:
    """
       Fast load of the pickled compact index.
       Returns a dict mapping each base_id to a dict with keys:
         - "categories": <space-separated category string>
         - "created":    <ISO date of version 1, e.g. "2007-03-31">
         - "authors":    <authors string>
         - "title":      <title string>

       Example return value:
         {
           "2309.00543": {
             "categories": "cs.LG stat.ML",
             "created":    "2023-09-01",
             "authors":    "A. Researcher and B. Scientist",
             "title":      "An Interesting Paper on Machine Learning"
           },
           ...
         }
       """
    if not os.path.exists(dest_path):
        raise FileNotFoundError(f"No such file: {dest_path}")

    print(f"[load] Unpickling '{dest_path}' …")
    with open(dest_path, "rb") as fin:
        index = pickle.load(fin)
    print(f"[load] Loaded {len(index):,} records.")
    return index




def list_arxiv_ids(
    regex_id:    str      = None,
    start_date:  str      = None,      # "YYYY-MM-DD"
    end_date:    str      = None,      # "YYYY-MM-DD"
    categories          = None,        # single str or list of str
    author:      str      = None,      # substring to match in rec["authors"]
    title:       str      = None,      # substring to match in rec["title"]
    update_arxiv_ids: bool = False,
    verbose:     bool     = False
) -> list:
    """
    Return arXiv IDs matching the given filters:
      - regex_id:   Python regex to match the base arXiv ID
      - start_date: earliest submission date ("YYYY-MM-DD")
      - end_date:   latest submission date  ("YYYY-MM-DD")
      - categories: single category or list of categories (e.g. "cs.LG")
      - author:     substring (case-insensitive) to match in the author field
      - title:      substring (case-insensitive) to match in the title field
      - update_arxiv_ids: if True, rebuild the local compact index from snapshot
      - verbose:    print debug statements

    First attempts a local lookup using the compact pickle (rebuilding if requested).
    If neither pickle nor snapshot is available, falls back to list_arxiv_ids_remote().
    """
    # Normalize categories into a list
    if isinstance(categories, str):
        categories = [categories]

    # ─── If update_arxiv_ids requested, force rebuild if snapshot exists ─────────────────
    if update_arxiv_ids and os.path.exists(ARXIV_META_DATA):
        if verbose:
            print("[list_arxiv_ids] Rebuilding compact index from snapshot…")
        meta_data_full_to_hdf5(overwrite = True, verbose   = verbose)

    # ─── Attempt local lookup if pickle or snapshot exists ───────────────────────────────
    if os.path.exists(ARXIV_META_DATA_HDF5) or os.path.exists(ARXIV_META_DATA):
        # If pickle missing but snapshot present, build it now
        if not os.path.exists(ARXIV_META_DATA_HDF5):
            if verbose:
                print("[list_arxiv_ids] Building compact index from snapshot…")
            meta_data_full_to_hdf5(overwrite = True, verbose = verbose)

        # Load the compact index (pickle)
        if verbose:
            print(f"[list_arxiv_ids] Loading local compact index: {ARXIV_META_DATA_HDF5}")
#        idx = load_meta_data_compact(ARXIV_META_DATA_COMPACT)

        # 1) Figure out which columns are actually needed
        needed_cols = []
        if start_date or end_date:
            needed_cols.append("created")
        if categories:
            needed_cols.append("categories")
        if author:
            needed_cols.append("authors")
        if title:
            needed_cols.append("title")

        # 2) Always include "base_id" under the hood; load only the needed columns
        idx = load_meta_data_hdf5(hdf5_path = ARXIV_META_DATA_HDF5, cols=needed_cols)

        # Call the local filtering function once
        return list_arxiv_ids_local(
            idx          = idx,
            regex_id     = regex_id,
            start_date   = start_date,
            end_date     = end_date,
            categories   = categories,
            author       = author,
            title        = title,
            update_arxiv_ids = False,
            verbose      = verbose
        )

    # ─── Otherwise fall back to remote API ───────────────────────────────────────────────
    if verbose:
        print("[list_arxiv_ids] No local data found; querying remote API…")

    return list_arxiv_ids_remote(
        start_date  = start_date,
        end_date    = end_date,
        categories  = categories,
        regex_id    = regex_id,
        author      = author,
        title       = title,
        verbose     = verbose
    )


def list_arxiv_ids_remote(
    start_date: str       = None,     # "YYYY-MM-DD"
    end_date:   str       = None,     # "YYYY-MM-DD"
    categories           = None,      # single str or list of str
    regex_id:   str       = None,     # regex to filter base IDs
    author:     str       = None,     # substring match (case-insensitive) in author field
    title:      str       = None,     # substring match (case-sensitive) in title field
    max_retries: int      = 5,
    batch_size: int       = 100,
    verbose:    bool      = False
) -> list:
    """
    Query the arXiv API (api/query) and then client-side filter on title substring (case-sensitive).
    Returns unique base-IDs matching:
      - start_date/end_date    -> submittedDate:[...]
      - categories             -> cat:filter
      - author (if provided)   -> au:"<author_substring>" (server-side, case-insensitive)
      - regex_id (if provided) -> Python regex on the base ID
      - title (if provided)    -> client-side case-sensitive substring check on <title>

    This ensures that `title="AI"` will match ANY occurrence of "AI" in a paper's title,
    even if it is embedded inside a larger word like "OpenAI".
    """
    # ─── Build date clause ───────────────────────────────────────────────
    def to_arxiv_dt(d_iso):
        return d_iso.replace("-", "") + "0000"

    date_clause = None
    if start_date and end_date:
        sd = to_arxiv_dt(start_date)
        ed = to_arxiv_dt(end_date).replace("0000", "2359")
        date_clause = f"submittedDate:[{sd} TO {ed}]"
    elif start_date:
        sd = to_arxiv_dt(start_date)
        date_clause = f"submittedDate:[{sd} TO 999999999999]"
    elif end_date:
        ed = to_arxiv_dt(end_date).replace("0000", "2359")
        date_clause = f"submittedDate:[000000000000 TO {ed}]"

    # ─── Build category clause ───────────────────────────────────────────
    if isinstance(categories, str):
        categories = [categories]
    cat_clause = None
    if categories:
        if len(categories) == 1:
            cat_clause = f"cat:{categories[0]}"
        else:
            joined = " OR ".join(f"cat:{c}" for c in categories)
            cat_clause = f"({joined})"  # e.g. "(cat:cs.LG OR cat:stat.ML)"

    # ─── Build author clause ─────────────────────────────────────────────
    author_clause = None
    if author:
        # au:<author_substring> is case-insensitive on the server side
        author_clause = f'au:"{author}"'

    # ─── Combine server-side clauses (date, category, author) with " AND "
    clauses = []
    for clause in (date_clause, cat_clause, author_clause):
        if clause:
            clauses.append(clause)
    search_query = " AND ".join(clauses) if clauses else "all"

    if verbose:
        print(f"[remote] Built search_query: {search_query!r}")

    base_url = "https://export.arxiv.org/api/query"
    start_index = 0
    ids_set = set()
    pat = re.compile(regex_id) if regex_id else None

    while True:
        params = {
            "search_query": search_query,
            "start":        start_index,
            "max_results":  batch_size,
            "sortBy":       "submittedDate",
            "sortOrder":    "ascending"
        }

        # ─── Fetch with retry logic ──────────────────────────────────────
        for attempt in range(1, max_retries + 1):
            try:
                r = requests.get(base_url, params=params, timeout=10)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt == max_retries:
                    raise
                wait = 2 ** attempt
                if verbose:
                    print(f"[remote] Error {e!r}, retrying in {wait}s...")
                time.sleep(wait)
        else:
            raise RuntimeError("Failed to connect to arXiv API after retries")

        # ─── Parse Atom feed ───────────────────────────────────────────────
        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            break

        for e in entries:
            # Extract <id>…</id>, e.g. "http://arxiv.org/abs/2309.00252v1"
            full_id = e.find("atom:id", ns).text.rsplit("/", 1)[-1]
            base_id = full_id.split("v")[0]

            # Server-side date double-check (optional)
            if date_clause:
                pub_date = e.find("atom:published", ns).text.split("T", 1)[0]
                if start_date and pub_date < start_date:
                    continue
                if end_date   and pub_date > end_date:
                    continue

            # Server-side regex on base_id
            if pat and not pat.search(base_id):
                continue

            # ─── Client-side title substring (case-sensitive) ──────────
            if title:
                title_text = e.find("atom:title", ns).text
                if title not in title_text:
                    continue

            # If we reach here, this paper passes all filters
            ids_set.add(base_id)
            if verbose:
                print(f"[remote] KEEP {base_id}")

        # If fewer entries than a full batch, done
        if len(entries) < batch_size:
            break
        start_index += batch_size

    result = sorted(ids_set)
    if verbose:
        print(f"[remote] Found {len(result)} unique base IDs.")
    return result



def list_arxiv_ids_local(
    idx=None,                  # type: Dict[str,Dict[str,str]]
    regex_id=None,
    start_date=None,           # "YYYY-MM-DD"
    end_date=None,             # "YYYY-MM-DD"
    categories=None,
    author=None,               # substring to match in rec["authors"]
    title=None,                # substring to match in rec["title"]
    update_arxiv_ids=False,
    verbose=False
):
    # If requested, rebuild the HDF5 index
    if update_arxiv_ids:
        if verbose:
            print("[list_arxiv_ids_local] Rebuilding compact HDF5 index…")
        meta_data_full_to_hdf5(overwrite = True, verbose=verbose)

    # If no pre-loaded idx was passed in, load only the columns we’ll need
    if idx is None:
        # Determine which columns are needed for filtering
        needed_cols = []
        if categories:
            needed_cols.append("categories")
        if start_date or end_date:
            needed_cols.append("created")
        if author:
            needed_cols.append("authors")
        if title:
            needed_cols.append("title")

        # Load only those columns (plus base_id implicitly)
        idx = load_meta_data_hdf5(
            hdf5_path = ARXIV_META_DATA_HDF5,
            cols      = needed_cols
        )

    if isinstance(categories, str):
        categories = [categories]

    pat_full = re.compile(regex_id) if regex_id else None

    # if regex_id contains a “v<number>”, build a second pattern that matches only the
    # base part (e.g. "^2309\.00543") against base_id itself:
    pat_base = None
    if regex_id:
        ver_match = re.search(r'(v\d+)$', regex_id)
        if ver_match:
            ver = ver_match.group(1)  # e.g. "v1"
            base_pattern = regex_id.replace(ver, '').rstrip('$')
            pat_base = re.compile(base_pattern)

    out = []
    for bid, rec in idx.items():
        # 1.1) if there was a versioned regex, match the stripped‐down pattern against base_id
        if pat_base:
            if not pat_base.search(bid):
                continue
        # 1.2) otherwise, if user supplied a plain regex (no “vX”), use that against base_id
        elif pat_full:
            if not pat_full.search(bid):
                continue

        # 2) Category filter
        if categories:
            cats = rec.get("categories", "").split()
            if not any(c in cats for c in categories):
                continue

        # 3) Author filter (case-sensitive substring)
        if author:
            authors_field = rec.get("authors", "")
            if author not in authors_field:
                continue

        # 4) Title filter (case-sensitive substring)
        if title:
            title_field = rec.get("title", "")
            if title not in title_field:
                continue

        # 5) Date filter
        cd = rec.get("created", "")
        if start_date and cd < start_date:
            continue
        if end_date and cd > end_date:
            continue

        out.append(bid)

    if verbose:
        print(f"[list_arxiv_ids_local] Found {len(out)} matching IDs.")

    return out


# Compute the directory where we store the full articles
def arxiv_dates_and_format_to_dir(ids, dates, format, output_dir = DATA_DIR + '/full_papers'):
#    print('format_to_dir: ids: ', ids, 'dates: ', dates, 'format: ', format)
    if format in ['source', 'latex']:
        format = 'tex'  # change dir
    return {id: output_dir + '/' + '/'.join(d.split("-")) + '/' + format for id, d in zip(ids, dates)}


def compute_num_paper_by_dates(start_date=None, end_date=None, update_arxiv_ids=False, verbose=False):
    return len(list_arxiv_ids(start_date=start_date, end_date=end_date, update_arxiv_ids=update_arxiv_ids, verbose=verbose))



def filter_ids_by_regex(
    regex_id,
    from_date=None,
    until_date=None,
    categories=None,
    author=None,
    title=None,
    update_arxiv_ids=False,
    data_dir=None,
    verbose=False
):
    """
    Returns two lists:
      - ids_no_version: base IDs matching the (possibly-versioned) regex AND other filters
      - ids_with_version: versioned IDs to fetch (e.g. '2309.00543v1')

    Now supports filtering by date range, categories, author, and title
    via list_arxiv_ids().
    """
    # Compile user’s regex if provided
    pat_full = re.compile(regex_id) if regex_id else None

    # ─── Load all base IDs that satisfy date/category/author/title filters ───────
    all_ids = list_arxiv_ids(
        regex_id         = None,
        start_date       = from_date,
        end_date         = until_date,
        categories       = categories,
        author           = author,
        title            = title,
        update_arxiv_ids = update_arxiv_ids,
        verbose          = verbose
    )

    if verbose:
#        print("Found these ids to filter: ", all_ids)
        print(f">>> filter_ids_by_regex: loaded {len(all_ids)} IDs")

    # ─── Determine which version suffix to attach ───────────────────────────────
    if regex_id:
        # If user’s regex mentions “v<number>”…
        ver_match = re.search(r'(v\d+)$', regex_id)
        if ver_match:
            ver = ver_match.group(1)  # e.g. "v1"
            # Strip off the “vX” part so we can match against base IDs
            base_pattern = regex_id.replace(ver, '').rstrip('$')
            pat_base = re.compile(base_pattern)

            # 1) Find base IDs via pat_base
            ids_no_version = [aid for aid in all_ids if pat_base.match(aid)]

            # 2) Re-attach version suffix and re-test full regex
            ids_with_version = [
                f"{aid}{ver}"
                for aid in ids_no_version
                if pat_full and pat_full.match(f"{aid}{ver}")
            ]
        else:
            # No “vX” in regex → treat it as matching v1 versions
            ids_no_version   = [aid for aid in all_ids if pat_full.match(aid)]
            ids_with_version = [f"{aid}v1" for aid in ids_no_version]
    else:
        # No regex at all → return all base IDs and their “v1” versions
        ids_no_version   = all_ids[:]
        ids_with_version = [f"{aid}v1" for aid in all_ids]

    if verbose:
        print(f">>> filter_ids_by_regex: {len(ids_no_version)} bases, "
              f"{len(ids_with_version)} versioned IDs")
    return ids_no_version, ids_with_version



def fetch_arxiv_metadata(
    versioned_ids: List[str],
    jsonl_path:    str = ARXIV_META_DATA,
    hdf5_path:     str = ARXIV_META_DATA_HDF5,
    columns: List[str] = None, # Which columns to extract (default: ALL OF THEM)
    verbose:       bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Given a list of versioned arXiv IDs (e.g. ["2309.00543v1", "2309.00176v1", …]),
    use the prebuilt HDF5 “offset” column to jump directly to each JSONL line in
    `jsonl_path` and return the full metadata JSON for each versioned ID.

    Returns a dict:
      {
        "2309.00543v1": { … full JSON metadata from JSONL, but with "id" replaced by "2309.00543v1" … },
        "2309.00176v1": { … },
        …
      }

    Any versioned ID whose base is not found in the HDF5 offsets table is skipped.

    Parameters
    ----------
    versioned_ids : list of str
        List of IDs with “vX” suffix, e.g. ["2309.00543v1", "2309.00176v1"].
    jsonl_path : str
        Path to the 4 GB NDJSON (arxiv-metadata-oai-snapshot.json). One JSON object per line.
    hdf5_path : str
        Path to the HDF5 file produced by `meta_data_full_to_hdf5`, which contains an
        “offset” column for every base_id.
    verbose : bool
        If True, print debug info for each ID found or missed.

    Usage example:
      data = fetch_arxiv_metadata(
          versioned_ids=["2309.00543v1", "2309.00176v1"],
          jsonl_path="…/arxiv-metadata-oai-snapshot.json",
          hdf5_path ="…/arxiv-compact.h5",
          verbose=True
      )
    """
    # 1) Extract base_ids from versioned_ids and load only those offsets
    base_ids_needed = []
    for vid in versioned_ids:
        if "v" in vid:
            base_ids_needed.append(vid.rsplit("v", 1)[0])
        else:
            base_ids_needed.append(vid)

    # Use efficient lookup for just the IDs we need (instead of loading all 2M+)
    offsets_dict = load_meta_data_hdf5_by_ids(base_ids_needed, hdf5_path, cols=["offset"])

    results: Dict[str, Dict[str, Any]] = {}

    # 2) Open the JSONL once for seeking
    with open(jsonl_path, "r", encoding="utf-8") as fin:
        for vid in versioned_ids:
            # Derive base_id by stripping off the trailing "v<digits>"
            if "v" in vid:
                base_id = vid.rsplit("v", 1)[0]
            else:
                base_id = vid

            entry = offsets_dict.get(base_id)
            if entry is None:
                if verbose:
                    print(f"[fetch_arxiv_metadata] Base ID '{base_id}' not found in offsets → skip")
                continue

            offset = entry["offset"]
            fin.seek(offset)
            line = fin.readline()
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                if verbose:
                    print(f"[fetch_arxiv_metadata] JSON parse error at offset {offset} for '{base_id}'")
                continue

            # Overwrite "id" to include the version suffix
            rec["id"] = vid

            # Ensure we have a consistent "published" or "created" field
            # (If any downstream logic expects "published", we can set it from v1-created)
            v1_created = rec.get("versions", [{}])[0].get("created", "")
            try:
                dt = parsedate_to_datetime(v1_created)
                rec["published"] = dt.isoformat()  # e.g. "2023-09-01T12:34:56"
            except Exception:
                # If parsing fails, leave "published" absent or empty
                rec["published"] = ""

            if columns is None:
                results[vid] = rec
            else: # Keep only relevant columns
                results[vid] = {"id": vid}
                for key in columns:
                    results[vid][key] = rec[key]

#            if verbose:
#                print(f"[fetch_arxiv_metadata] Loaded metadata for '{vid}' (offset={offset})")

    return results



def fetch_arxiv_batch(
    regex_id=None,
    start_date=None,
    end_date=None,
    category=None,
    author=None,
    title=None,
    formats="metadata", #     batch_size: int   = 200,
    output_dir: str = DATA_DIR + '/full_papers', # default: save in tree,  None, # don't save output
    force_update: bool = False,
    verbose: bool     = False
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch arXiv items by filtering IDs and retrieving requested formats.

    regex_id    : str (regex) to match IDs; e.g. '^2309.00543v1$'
    start_date  : 'YYYY-MM-DD' publication start
    end_date    : 'YYYY-MM-DD' publication end
    category    : arXiv category filter (str or list of str)
    author      : substring to match in authors
    title       : substring to match in title
    formats     : single or list of 'metadata','abstract','pdf','html','source'
    batch_size  : API pagination size (unused for local fetch)
    output_dir  : save files here if provided
    verbose     : print debug

    Returns dict[id -> {format: data_or_path, ...}]
    """
    # ─── Normalize formats ──────────────────────────────────────────────
    if isinstance(formats, str):
        formats = [formats]
    if 'latex' in formats:
        formats[formats.index('latex')] = 'source'
    if 'tex' in formats:
        formats[formats.index('tex')] = 'source'
    formats = list(set(formats))

    # ─── Stage 1: FILTER IDs ────────────────────────────────────────────
    if verbose:
        print(f"[DEBUG] Filtering IDs with regex={regex_id!r}, "
            f"date={start_date}–{end_date}, category={category}, "
            f"author={author}, title={title}")

    ids_no_ver, ids_with_ver = filter_ids_by_regex(
        regex_id         = regex_id,
        from_date        = start_date,
        until_date       = end_date,
        categories       = category,
        author           = author,
        title            = title,
        update_arxiv_ids = False,
        data_dir         = os.path.dirname(ARXIV_META_DATA),
        verbose          = verbose)

    if verbose:
        print(f"[DEBUG] {len(ids_no_ver)} base IDs, {len(ids_with_ver)} versioned IDs to process")

    # ─── Stage 1a: If metadata is requested, fetch in one shot via local JSONL + HDF5 ───
    # If the user explicitly asked for “metadata” itself, we’ll load all:
    if "metadata" in formats:
        needed = None  # None → tells fetch_arxiv_metadata “give me the entire JSON blob”
    else:
        needed = ["published"]
        if category is not None:
            needed.append("categories")
        if author is not None:
            needed.append("authors")
        if title is not None:
            needed.append("title")

    if verbose:
        print("[DEBUG] Fetching metadata for all versioned IDs via local JSONL + HDF5 offsets…")
        print("IDS After Filtering:", ids_with_ver, "\n Columns needed:", needed)
    all_meta = fetch_arxiv_metadata(versioned_ids = ids_with_ver, verbose = verbose, columns=needed)
    # No further date/category/author/title checks needed: filter_ids_by_regex already did them.
    id_meta = all_meta.copy()

    # ─── Early return if only metadata was requested ──────────────────────
    if formats == ['metadata']:
        if verbose:
            print(f"[DEBUG] Returning all titles: {[id_meta[m]['title'] for m in id_meta]} ")

        id_meta = {
            outer_key: {'metadata': inner_dict}
            for outer_key, inner_dict in id_meta.items()}
        return id_meta

    # ─── Stage 2: RETRIEVE OTHER FORMATS ─────────────────────────────────
    # Set output dir for each file and format separately:
    ext_map = {'pdf': 'pdf', 'html': 'html', 'source': 'tar.gz'}

#    if verbose:
#        print("id_meta:", id_meta)
#        print(f"[DEBUG] Output dates: {[id_meta[m]['published'][:10] for m in id_meta]}")
    if output_dir: # Not None
        output_dirs = {res: None for res in formats}  # Create empty dict
        for res in formats:
            if output_dir == DATA_DIR + '/full_papers': # Default place to store all in a tree structure
                output_dirs[res] = arxiv_dates_and_format_to_dir([id for id in id_meta],
                                                                 [id_meta[m]['published'][:10] for m in id_meta], res, output_dir)
            else:
                output_dirs[res] = {id:output_dir for id in id_meta}  # all the same

    if verbose:
        print(f"[DEBUG] Output dir: {output_dir}")
#        print(f"[DEBUG] Output dirs: {output_dirs}")

    results: Dict[str, Dict[str, Any]] = {}
    for aid, meta in id_meta.items():
#        if verbose:
#            print(f"[DEBUG] Processing {aid} for formats: {formats}")

        entry: Dict[str, Any] = {}

        # Include metadata & abstract if needed
        if 'metadata' in formats:
            entry['metadata'] = meta
        if 'abstract' in formats:
            entry['abstract'] = meta.get('abstract', '')

        # For each of pdf/html/source, attempt download
        for res in formats:
            if res == 'metadata':  # already loaded
                continue
            if output_dir:
                if res == 'source':
                    filename = f"{aid}.tex"
                else:
                    filename = f"{aid}.{ext_map[res]}"
                local_path = os.path.join(output_dirs[res][aid], filename)
                if os.path.isfile(local_path):  # Found file locally
                    # Extract locally (different for different formats)
                    if res == 'pdf':
                        with open(local_path, 'rb') as f:
                            entry['pdf'] = f.read()
                    elif res == 'html':
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                            entry['html'] = f.read().splitlines()
                    elif res == 'source':
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                            entry['source'] = f.read().splitlines()

                    if verbose:
                        print(f"[DEBUG] Loading locally {res} for {aid} from {local_path}")
                    continue # do not download from web

            if res in ('pdf', 'html', 'source'):
                url = {
                    'pdf':    f'https://arxiv.org/pdf/{aid}.pdf',
                    'html':   f'https://arxiv.org/abs/{aid}',
                    'source': f'https://arxiv.org/e-print/{aid}'
                }[res]

                if verbose:
                    print(f"[DEBUG] Downloading {res} for {aid} from {url}")
                try:
                    resp = requests.get(url, timeout=10)
                    resp.raise_for_status()
                    cd = resp.headers.get('Content-Disposition', '')
                    url_filename = None
                    if 'filename=' in cd:
                        # simple regex to extract filename
                        m = re.search(r'filename="?([^"]+)"?', cd)
                        if m:
                            url_filename = m.group(1)

                except HTTPError as http_err:
                    print(f"Warning: could not download {url} — HTTP error: {http_err}")
                    continue
                except RequestException as req_err:
                    # catches other errors (connection, timeout, invalid URL, etc.)
                    print(f"Warning: request failed for {url} — {req_err}")
                    continue
                raw = resp.content

                if res == 'pdf':
                    entry['pdf'] = raw

                elif res == 'html':
                    # Split HTML into lines for convenience
                    entry['html'] = raw.decode('utf-8').splitlines()

                elif res == 'source':
                    buf = io.BytesIO(raw)
                    source_lines = None

                    # 1) Try as a tar.gz archive
                    try:
                        with tarfile.open(fileobj=buf, mode='r:gz') as tf:
                            tex_files = [n for n in tf.getnames() if n.endswith('.tex')]
                            if tex_files:
                                fobj = tf.extractfile(tex_files[0])
                                data = fobj.read() if fobj is not None else b''
                                try:
                                    content = data.decode('utf-8')
                                except UnicodeDecodeError:
                                    content = data.decode('utf-8', errors='ignore')
                                source_lines = content.splitlines()
                    except tarfile.ReadError:
                        # 2) Fallback: maybe it’s a single .tex file gzipped .gz
                        try:
                            decompressed = gzip.decompress(raw)
                            try:
                                content = decompressed.decode('utf-8')
                            except UnicodeDecodeError:
                                content = decompressed.decode('utf-8', errors='ignore')
                            source_lines = content.splitlines()
                        except Exception:
                            if verbose:
                                print(f"[WARN] Could not unpack source for {aid} as tar.gz or gzip. ; file name is  {url_filename} ; Skipping.")
                            source_lines = None
                    entry['source'] = source_lines

                # If output_dir is set, save raw bytes to disk
                if res in ('pdf', 'html', 'source') and output_dir: # save locally if needed
                    os.makedirs(output_dirs[res][aid], exist_ok=True)
                    if res == 'source':
                        filename = f"{aid}.tex"
                    else:
                        filename = f"{aid}.{ext_map[res]}"
                    path = os.path.join(output_dirs[res][aid], filename)
                    if res == 'source':
                        if entry.get('source') is None:  # Couldn't fetch source
                            if verbose:
                                print(f"[DEBUG] No valid source for {aid}, skipping save")
                        else:
                            with open(path, 'w', encoding='utf-8', errors='ignore') as f:
                                # Join lines with newline (you can also write `content` directly)
                                f.write("\n".join(entry.get('source', [])))
                    else:
                        with open(path, 'wb') as f:
                            f.write(raw)
                    if verbose:
                        print(f"[DEBUG] Saved {res} to {path}")
                    entry[f"{res}_path"] = path

#        print("At the end of entry: ", entry['metadata'])
        results[aid] = entry

    return results

# Helper
def find_main_tex(root: Path, arxiv_id: str) -> Optional[Path]:
    all_tex = list(root.rglob("*.tex"))
    if not all_tex:
        return None

    # 1. exact arXiv id
    for f in all_tex:
        if arxiv_id in f.name:
            return f

    # 2. common names
    common = ["main.tex", "paper.tex", "ms.tex", "article.tex"]
    for f in all_tex:
        if f.name in common:
            return f

    # 3. fallback: largest file
    return max(all_tex, key=lambda p: p.stat().st_size)



def fetch_arxiv_source(arxiv_id: str, dest_dir: Path, verbose: bool = False) -> Path:
    """
    Download arXiv source into dest_dir and return path to the main .tex file.
    Handles:
        - normal .tar.gz source
        - .tar without gzip
        - raw .tex mislabeled as gzip or tar
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Clean directory from previous attempts
    for p in dest_dir.iterdir():
        if p.is_file():
            p.unlink()
        else:
            shutil.rmtree(p)

    # -----------------------
    # 1. Download file
    # -----------------------
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    if verbose:
        print(f"[INFO] Downloading {arxiv_id} from {url}")

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    raw = resp.content

    # Save initial bytes
    gz_path = dest_dir / f"{arxiv_id}.tar.gz"
    gz_path.write_bytes(raw)

    # -----------------------
    # 2. Try GZIP decompress
    # -----------------------
    try:
        if verbose:
            print("[DEBUG] Attempting gzip decompression…")

        decompressed = gzip.decompress(raw)
        if verbose:
            print("[DEBUG] gzip decompression succeeded.")

    except Exception:
        # → Not gzip; maybe raw tex
        if verbose:
            print("[DEBUG] gzip failed → treat as raw tex.")
        tex_path = dest_dir / f"{arxiv_id}.tex"
        tex_path.write_bytes(raw)
        return tex_path

    # -----------------------
    # 3. After gzip: tar or raw tex?
    # -----------------------
    # Heuristic: tar headers contain "ustar" or other magic bits.
    if b"ustar" not in decompressed[:500] and not tarfile.is_tarfile(gz_path):
        # Probably raw tex mislabeled as gzip
        if verbose:
            print("[DEBUG] gzip output is not a tar → treat as raw tex.")
        tex_path = dest_dir / f"{arxiv_id}.tex"
        tex_path.write_bytes(decompressed)
        return tex_path

    # -----------------------
    # 4. Try to extract tar
    # -----------------------
    tar_path = dest_dir / f"{arxiv_id}.tar"
    tar_path.write_bytes(decompressed)

    if verbose:
        print("[DEBUG] Attempting tar extraction…")

    try:
        with tarfile.open(tar_path, "r:") as tf:
            tf.extractall(dest_dir)
    except Exception:
        # Fallback: system tar
        if verbose:
            print("[WARN] Python tar failed → trying system `tar`.")
        try:
            subprocess.run(
                ["tar", "-xf", str(tar_path), "-C", str(dest_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as e2:
            raise RuntimeError(
                f"Failed to extract tar archive for {arxiv_id}: {e2}"
            )

    # -----------------------
    # 5. Find .tex files (recursive)
    # -----------------------
    tex_files = list(dest_dir.rglob("*.tex"))
    if not tex_files:
        raise RuntimeError(f"No .tex found in {dest_dir} after extracting {arxiv_id}")

    # 5a. Prefer files containing \begin{document}
    doc_candidates = []
    for p in tex_files:
        try:
            txt = p.read_text(errors="ignore")
            if "\\begin{document}" in txt:
                doc_candidates.append(p)
        except Exception:
            continue

    candidates = doc_candidates if doc_candidates else tex_files

    # Normalize arxiv ID (drop version)
    base_id = arxiv_id.split("v")[0]

    # 5b. Prefer file that contains arxiv_id or base_id anywhere in filename
    for p in candidates:
        name = p.name.lower()
        if arxiv_id.lower() in name or base_id.lower() in name:
            return p

    # 5c. Common main filename heuristics
    common_main = {"main.tex", "paper.tex", "ms.tex", "article.tex"}
    for p in candidates:
        if p.name in common_main:
            return p

    # 5d. Fallback: largest .tex file
    return max(candidates, key=lambda p: p.stat().st_size)





# at top of file you already import shutil, pathlib, etc. (shutil is present)

def resolve_source_to_tex_local_first(base_id: str, meta: dict, full_papers_dir: Path, verbose: bool = False):
    """
    Local-first resolver:
      1. Determine the latest version from metadata.
      2. Determine correct year/month/day directory from metadata.
      3. Look for tex in full_papers/<year>/<month>/<day>/tex/<versioned_id>.tex
      4. If missing → fetch_arxiv_source to that directory and use the main .tex it returns.
    Returns: (Path to canonical tex file, versioned_id)
    """

    # --- 1. Determine version ---
    versions = meta.get("versions", [])
    if versions:
        version_tag = versions[-1].get("version", "v1")
    else:
        version_tag = "v1"

    versioned_id = f"{base_id}{version_tag}"

    # --- 2. Determine date directory ---
    pub = meta.get("published") or meta.get("created") or ""
    pub_date = str(pub)[:10]  # 'YYYY-MM-DD'
    try:
        year, month, day = pub_date.split("-")
    except ValueError:
        year, month, day = ("unknown", "unknown", "unknown")

    # build tex directory path
    tex_dir = full_papers_dir / year / month / day / "tex"
    tex_dir.mkdir(parents=True, exist_ok=True)

    tex_path = tex_dir / f"{versioned_id}.tex"

    # --- 3. Local-first check ---
    if tex_path.exists():
        if verbose:
            print(f"[DEBUG] Using local TEX: {tex_path}")
        return tex_path, versioned_id

    # --- 4. If missing -> fetch directly from arXiv ---
    if verbose:
        print(f"[DEBUG] Local TEX missing. Fetching source for {versioned_id} into {tex_dir}")

    try:
        # IMPORTANT: this returns the path to the main .tex file in the unpacked source
        main_tex = fetch_arxiv_source(versioned_id, tex_dir, verbose=verbose)
    except Exception as e:
        raise RuntimeError(f"fetch_arxiv_source failed for {versioned_id}: {e}")

    # --- 5. Canonicalise the main tex file ---
    if main_tex is not None:
        main_tex = Path(main_tex)
        if main_tex.exists():
            if verbose:
                print(f"[DEBUG] fetch_arxiv_source resolved main TEX -> {main_tex}")
            # Prefer to have a canonical <versioned_id>.tex
            if main_tex.resolve() != tex_path.resolve():
                try:
                    shutil.copy(main_tex, tex_path)
                    if verbose:
                        print(f"[DEBUG] Copied main TEX {main_tex.name} -> {tex_path.name}")
                except OSError as e:
                    if verbose:
                        print(f"[WARN] Failed to copy main TEX {main_tex} to {tex_path}: {e}")
                    # fallback: just use the actual main_tex path
                    tex_path = main_tex
            else:
                tex_path = main_tex
        else:
            # main_tex path is bogus → fall back to generic search below
            main_tex = None

    # --- 6. Very defensive fallback: any *.tex in tex_dir ---
    if not tex_path.exists():
        tex_files = sorted(
            tex_dir.rglob("*.tex"),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if tex_files:
            tex_path = tex_files[0]
            if verbose:
                print(
                    f"[WARN] No canonical {versioned_id}.tex, "
                    f"using largest TEX file {tex_path.name}"
                )
        else:
            raise FileNotFoundError(f"No .tex found in {tex_dir} after fetching")

    return tex_path, versioned_id
