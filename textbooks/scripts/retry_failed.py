#!/usr/bin/env python3
"""
Second pass: use url_overrides.json to retry books that failed the first pass.
Only attempts books whose book_id has a non-comment key in the overrides file.
Updates download_status.json in place.
"""

import csv
import json
import logging
from pathlib import Path

from download_books import (
    OUT_BASE,
    PDF_DIR,
    LOG_FILE,
    STATUS_JSON,
    CSV_PATH,
    book_filename,
    stream_to_file,
    http_get,
)

OVERRIDES_JSON = Path(__file__).parent / "url_overrides.json"


def main():
    overrides = {k: v for k, v in json.loads(OVERRIDES_JSON.read_text()).items()
                 if not k.startswith("_") and not k.endswith("_note")}
    print(f"Loaded {len(overrides)} URL overrides")

    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format="%(asctime)s %(levelname)s RETRY %(message)s",
    )

    # Load CSV for metadata
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        csv_rows = {r["book_id"]: r for r in csv.DictReader(f)}

    # Load current status
    status = {r["book_id"]: r for r in json.loads(STATUS_JSON.read_text())}

    for bid, url in overrides.items():
        row = csv_rows.get(bid)
        if not row:
            print(f"[skip] {bid} not in CSV")
            continue
        dest = PDF_DIR / book_filename(bid, row["authors"], row["title"])
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"[cached] {bid} {dest.name}")
            # Make sure status reflects the cached file, not a stale prior failure
            prev = status.get(bid, {})
            sz = dest.stat().st_size
            if prev.get("status") != "ok" or prev.get("bytes") != sz:
                status[bid] = {"book_id": bid, "status": "ok",
                               "path": str(dest.relative_to(OUT_BASE)),
                               "bytes": sz,
                               "via": prev.get("via") or f"override-cached:{url}"}
            continue

        try:
            if url.lower().split("?")[0].endswith(".pdf"):
                size = stream_to_file(url, dest)
                status[bid] = {"book_id": bid, "status": "ok",
                               "path": str(dest.relative_to(OUT_BASE)),
                               "bytes": size, "via": f"override-direct:{url}"}
                print(f"[ok] {bid} {size//1024}KB")
            else:
                r = http_get(url)
                ctype = r.headers.get("Content-Type", "").lower()
                if "pdf" in ctype or r.content[:4] == b"%PDF":
                    dest.write_bytes(r.content)
                    status[bid] = {"book_id": bid, "status": "ok",
                                   "path": str(dest.relative_to(OUT_BASE)),
                                   "bytes": len(r.content),
                                   "via": f"override-redirect:{url}"}
                    print(f"[ok] {bid} {len(r.content)//1024}KB (after redirect)")
                else:
                    raise RuntimeError(f"ctype={ctype}, head={r.content[:20]!r}")
        except Exception as e:
            status[bid] = {"book_id": bid, "status": "fail",
                           "reason": str(e)[:200], "url": url, "via": "override"}
            print(f"[fail] {bid} {str(e)[:120]}")

    STATUS_JSON.write_text(json.dumps(list(status.values()), indent=2))
    # Print summary
    summary = {}
    for r in status.values():
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    print("\n=== UPDATED SUMMARY ===")
    for k, v in sorted(summary.items()):
        print(f"  {k:10s} {v}")
    total_mb = sum(r.get("bytes", 0) for r in status.values()
                   if r["status"] in ("ok", "cached")) / (1024*1024)
    print(f"  total     {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
