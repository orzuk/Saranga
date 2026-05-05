#!/usr/bin/env python3
"""
Download openly-licensed textbooks listed in undergrad_textbooks.csv.

Output:
    textbooks/pdf/bXXX_<slug>.pdf      one PDF per book (when discoverable)
    textbooks/downloads.log            per-file outcome
    textbooks/download_status.json     structured summary for follow-up

Handles:
    - direct .pdf URLs
    - arxiv.org/abs/ID  -> arxiv.org/pdf/ID.pdf
    - landing-page HTML -> scrape first reasonable .pdf link
    - openstax.org detail pages -> scrape the "Download the PDF" asset link
    - redirect chains, 429 backoff, size caps, content-type sniffing
"""

import csv
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# -- paths ---------------------------------------------------------------
CSV_PATH = Path("/mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv")
OUT_BASE = Path(__file__).resolve().parents[1]
PDF_DIR = OUT_BASE / "pdf"
SRC_DIR = OUT_BASE / "source"
LOG_FILE = OUT_BASE / "downloads.log"
STATUS_JSON = OUT_BASE / "download_status.json"

DOWNLOADABLE = {"PUBLIC_DOMAIN", "CC", "AUTHOR_POSTED", "OPEN_LICENSED"}
UA = (
    "Mozilla/5.0 (X11; Linux x86_64; research-textbook-fetcher) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = 90
MAX_MB = 300
MAX_WORKERS = 6
RETRIES = 2

SESSION_HEADERS = {"User-Agent": UA, "Accept": "*/*"}


# -- naming --------------------------------------------------------------
def slugify(text: str, limit: int = 40) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return text.strip("_")[:limit]


def book_filename(book_id: str, authors: str, title: str) -> str:
    first = authors.split(";")[0].split(",")[0].strip()
    if " " in first:
        first = first.split()[-1]  # last word ~ surname
    author_slug = slugify(first, 20) or "anon"
    title_slug = slugify(title.split(":")[0], 30) or "book"
    return f"{book_id}_{author_slug}_{title_slug}.pdf"


# -- url logic -----------------------------------------------------------
ARXIV_ABS = re.compile(r"^(https?://arxiv\.org)/abs/([\w./\-]+)(v\d+)?/?$")


def normalize_url(url: str) -> str:
    url = url.strip()
    m = ARXIV_ABS.match(url)
    if m:
        return f"{m.group(1)}/pdf/{m.group(2)}.pdf"
    return url


def openstax_pdf_url(html: str, base: str) -> str | None:
    """OpenStax /details/books/... pages list downloads. Find the student PDF."""
    # Typical pattern: https://assets.openstax.org/.../<Title>-OP.pdf
    m = re.search(r'https://assets\.openstax\.org/[^"\'\s]+?-OP\.pdf', html)
    if m:
        return m.group(0)
    # Fall back: any assets.openstax.org *.pdf
    m = re.search(r'https://assets\.openstax\.org/[^"\'\s]+?\.pdf', html)
    return m.group(0) if m else None


PDF_LINK_RE = re.compile(r'href\s*=\s*["\']([^"\']+?\.pdf[^"\']*)["\']', re.IGNORECASE)
PDF_BAD_HINTS = (
    "sample",
    "preview",
    "errata",
    "solutions",
    "syllabus",
    "cover",
    "toc",
)


def pick_best_pdf(html: str, base_url: str) -> str | None:
    candidates = [urljoin(base_url, h) for h in PDF_LINK_RE.findall(html)]
    # Deduplicate, preserve order
    seen, uniq = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    # Prefer ones NOT matching bad hints
    good = [c for c in uniq if not any(h in c.lower() for h in PDF_BAD_HINTS)]
    return (good or uniq or [None])[0]


# -- http ----------------------------------------------------------------
def http_get(url: str, stream: bool = False) -> requests.Response:
    last_exc = None
    for attempt in range(RETRIES + 1):
        try:
            r = requests.get(
                url,
                headers=SESSION_HEADERS,
                timeout=TIMEOUT,
                allow_redirects=True,
                stream=stream,
            )
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_exc = e
            time.sleep(2 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def stream_to_file(url: str, dest: Path) -> int:
    with http_get(url, stream=True) as r:
        ctype = r.headers.get("Content-Type", "").lower()
        total = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                total += len(chunk)
                if total > MAX_MB * 1024 * 1024:
                    f.close()
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError(f"exceeded {MAX_MB}MB cap")
        # Verify PDF magic bytes
        with open(tmp, "rb") as f:
            head = f.read(4)
        if head != b"%PDF" and "pdf" not in ctype:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"not a PDF (head={head!r}, ctype={ctype})")
        tmp.rename(dest)
        return total


# -- per-book ------------------------------------------------------------
def process_book(row: dict) -> dict:
    bid = row["book_id"]
    url_raw = row.get("url", "").strip()
    if not url_raw or url_raw.upper() == "UNKNOWN":
        return {"book_id": bid, "status": "skip", "reason": "no url"}

    url = normalize_url(url_raw)
    dest = PDF_DIR / book_filename(bid, row["authors"], row["title"])

    if dest.exists() and dest.stat().st_size > 10_000:
        return {
            "book_id": bid,
            "status": "cached",
            "path": str(dest.relative_to(OUT_BASE)),
            "bytes": dest.stat().st_size,
        }

    try:
        # First look: is the URL itself a PDF?
        if url.lower().split("?")[0].endswith(".pdf"):
            size = stream_to_file(url, dest)
            return {
                "book_id": bid,
                "status": "ok",
                "path": str(dest.relative_to(OUT_BASE)),
                "bytes": size,
                "via": "direct",
            }

        # Fetch as page, then decide
        r = http_get(url)
        ctype = r.headers.get("Content-Type", "").lower()
        if "pdf" in ctype or r.content[:4] == b"%PDF":
            dest.write_bytes(r.content)
            return {
                "book_id": bid,
                "status": "ok",
                "path": str(dest.relative_to(OUT_BASE)),
                "bytes": len(r.content),
                "via": "direct-after-redirect",
            }

        if "html" in ctype or "<html" in r.text[:5000].lower():
            resolved = str(r.url)
            # Domain-specific rules
            if "openstax.org" in resolved:
                target = openstax_pdf_url(r.text, resolved)
            else:
                target = pick_best_pdf(r.text, resolved)
            if not target:
                return {
                    "book_id": bid,
                    "status": "fail",
                    "reason": "html page, no pdf link found",
                    "url": resolved,
                }
            size = stream_to_file(target, dest)
            return {
                "book_id": bid,
                "status": "ok",
                "path": str(dest.relative_to(OUT_BASE)),
                "bytes": size,
                "via": f"scraped:{target}",
            }

        return {
            "book_id": bid,
            "status": "fail",
            "reason": f"unexpected content-type {ctype}",
            "url": str(r.url),
        }

    except Exception as e:
        return {
            "book_id": bid,
            "status": "fail",
            "reason": str(e)[:200],
            "url": url,
        }


# -- main ----------------------------------------------------------------
def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    SRC_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r.get("license_status", "").strip() in DOWNLOADABLE
            and r.get("url", "").strip()
            and r.get("url", "").strip().upper() != "UNKNOWN"
        ]

    print(f"Queueing {len(rows)} books from {len(open(CSV_PATH).readlines())-1} total")
    logging.info(f"Queueing {len(rows)} books")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process_book, r): r for r in rows}
        for i, fut in enumerate(as_completed(futures), 1):
            r = futures[fut]
            out = fut.result()
            results.append(out)
            line = f"[{i:3d}/{len(rows)}] {out['book_id']} {out['status']:8s} {out.get('path') or out.get('reason','')}"
            print(line)
            logging.info(line)

    STATUS_JSON.write_text(json.dumps(results, indent=2))

    summary = {}
    for res in results:
        summary.setdefault(res["status"], 0)
        summary[res["status"]] += 1
    print("\n=== SUMMARY ===")
    for k, v in sorted(summary.items()):
        print(f"  {k:10s} {v}")
    total_bytes = sum(r.get("bytes", 0) for r in results if r["status"] in ("ok", "cached"))
    print(f"  total      {total_bytes / (1024*1024):.1f} MB downloaded")
    logging.info(f"SUMMARY: {summary}")


if __name__ == "__main__":
    main()
