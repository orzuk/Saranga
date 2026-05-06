#!/usr/bin/env python3
"""
Standalone sanity-check: download 100 arXiv math paper sources
(10 per year for 10 years) and count how many .tex files each contains.
"""

import io
import gzip
import tarfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

YEARS = [1995, 2000, 2002, 2005, 2007, 2009, 2012, 2015, 2017, 2020]
PER_YEAR = 10
ARXIV_API = "http://export.arxiv.org/api/query"
EPRINT_URL = "https://arxiv.org/e-print/"

def fetch_paper_ids(year: int, n: int = PER_YEAR) -> list[str]:
    """Query arXiv API for n math papers submitted in the given year."""
    # arXiv API date range filter
    query = (
        f"search_query=cat:math.*"
        f"+AND+submittedDate:[{year}0101+TO+{year}1231]"
        f"&start=0&max_results={n}&sortBy=submittedDate&sortOrder=ascending"
    )
    url = f"{ARXIV_API}?{query}"
    print(f"  Querying arXiv API for {year}...")
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-tex-survey/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    ids = []
    for entry in root.findall("atom:entry", ns):
        id_url = entry.find("atom:id", ns).text  # e.g. http://arxiv.org/abs/2005.12345v1
        arxiv_id = id_url.split("/abs/")[-1]
        ids.append(arxiv_id)
    return ids


def count_tex_in_source(arxiv_id: str) -> int | str:
    """
    Download the e-print source and count .tex files.
    Returns int (number of .tex files) or a string describing the format if unexpected.
    """
    url = f"{EPRINT_URL}{arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-tex-survey/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        content_type = resp.headers.get("Content-Type", "")

    # Try to open as tar.gz first (most common for multi-file submissions)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            names = tar.getnames()
            tex_files = [n for n in names if n.lower().endswith(".tex")]
            return len(tex_files)
    except (tarfile.TarError, gzip.BadGzipFile, EOFError):
        pass

    # Try plain gzip (single .tex file compressed)
    try:
        decompressed = gzip.decompress(raw)
        # If it decompresses and looks like LaTeX, it's a single .tex
        if b"\\begin" in decompressed or b"\\document" in decompressed or b"\\" in decompressed:
            return 1
        return "gzip-non-tex"
    except (gzip.BadGzipFile, EOFError):
        pass

    # Try as plain tar (uncompressed)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
            names = tar.getnames()
            tex_files = [n for n in names if n.lower().endswith(".tex")]
            return len(tex_files)
    except tarfile.TarError:
        pass

    # Raw text?
    if b"\\begin" in raw or b"\\document" in raw:
        return 1

    return "unknown-format"


def main():
    results = []  # list of (year, arxiv_id, tex_count_or_status)

    for year in YEARS:
        ids = fetch_paper_ids(year)
        if not ids:
            print(f"  WARNING: No papers found for {year}")
            continue
        print(f"  Found {len(ids)} papers for {year}, downloading sources...")

        for i, aid in enumerate(ids):
            try:
                tex_count = count_tex_in_source(aid)
                results.append((year, aid, tex_count))
                print(f"    [{i+1}/{len(ids)}] {aid}: {tex_count} tex file(s)")
            except Exception as e:
                results.append((year, aid, f"error: {e}"))
                print(f"    [{i+1}/{len(ids)}] {aid}: ERROR - {e}")
            # Be polite to arXiv servers
            time.sleep(1)

        # Pause between year batches (arXiv rate limit: ~1 req/3s)
        time.sleep(3)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    numeric = [(y, aid, c) for y, aid, c in results if isinstance(c, int)]
    non_numeric = [(y, aid, c) for y, aid, c in results if not isinstance(c, int)]

    single_tex = [(y, aid) for y, aid, c in numeric if c == 1]
    multi_tex = [(y, aid, c) for y, aid, c in numeric if c > 1]
    zero_tex = [(y, aid) for y, aid, c in numeric if c == 0]

    print(f"\nTotal papers processed:  {len(results)}")
    print(f"  Single .tex file:     {len(single_tex)}")
    print(f"  Multiple .tex files:  {len(multi_tex)}")
    print(f"  Zero .tex files:      {len(zero_tex)}")
    print(f"  Errors/unknown:       {len(non_numeric)}")

    if multi_tex:
        print(f"\n── Papers with multiple .tex files ──")
        for y, aid, c in multi_tex:
            print(f"  {y}  {aid}: {c} .tex files")

    if zero_tex:
        print(f"\n── Papers with 0 .tex files (tar with no .tex) ──")
        for y, aid in zero_tex:
            print(f"  {y}  {aid}")

    if non_numeric:
        print(f"\n── Errors / unknown formats ──")
        for y, aid, c in non_numeric:
            print(f"  {y}  {aid}: {c}")

    # Per-year breakdown
    print(f"\n── Per-year breakdown ──")
    by_year = defaultdict(lambda: {"single": 0, "multi": 0, "zero": 0, "other": 0})
    for y, aid, c in results:
        if isinstance(c, int):
            if c == 1:
                by_year[y]["single"] += 1
            elif c > 1:
                by_year[y]["multi"] += 1
            else:
                by_year[y]["zero"] += 1
        else:
            by_year[y]["other"] += 1

    print(f"  {'Year':<6} {'Single':<8} {'Multi':<8} {'Zero':<6} {'Error':<6}")
    for y in YEARS:
        d = by_year[y]
        print(f"  {y:<6} {d['single']:<8} {d['multi']:<8} {d['zero']:<6} {d['other']:<6}")


if __name__ == "__main__":
    main()
