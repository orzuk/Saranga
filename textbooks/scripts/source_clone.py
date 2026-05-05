#!/usr/bin/env python3
"""
Fetch LaTeX / PreTeXt / Jupyter source for textbooks where it's available.
PreTeXt XML and LaTeX source extract far more cleanly than PDFs.

Output:
    textbooks/source/bXXX_<slug>/   cloned repo OR unpacked tarball
    textbooks/source_status.json    per-book outcome

Mechanisms:
    method="git"     : git clone <url> <dest>
    method="tarball" : curl <url> -> tar xz / unzip -> <dest>
    method="skip"    : known-unavailable, documented

Edit SOURCE_MAP below as more LaTeX sources are discovered.
"""

import csv
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

OUT_BASE = Path(__file__).resolve().parents[1]
SRC_DIR = OUT_BASE / "source"
STATUS_JSON = OUT_BASE / "source_status.json"
CSV_PATH = Path("/mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv")

UA = "Mozilla/5.0 (research-textbook-source-fetcher; academic use)"
GIT_DEPTH = 1  # shallow clone — we only need the source, not history

# -----------------------------------------------------------------------
# SOURCE_MAP — curated list of books with known LaTeX/PreTeXt source.
#
# Keys are book_ids from undergrad_textbooks.csv.  method="git" uses
# shallow git clone; method="tarball" downloads and unpacks a .tar.gz
# or .zip.  method="skip" documents why the source is unreachable.
# -----------------------------------------------------------------------
SOURCE_MAP = {
    # --- PreTeXt XML (cleanest targets) --------------------------------
    "b026": {
        "method": "git",
        "url": "https://github.com/twjudson/aata.git",
        "slug": "judson_aata_pretext",
        "note": "Abstract Algebra: Theory and Applications (Judson). PreTeXt source.",
    },
    "b029": {
        "method": "git",
        "url": "https://github.com/oscarlevin/discrete-book.git",
        "slug": "levin_discrete_pretext",
        "note": "Discrete Mathematics: An Open Introduction (Levin). PreTeXt source.",
    },

    # --- LaTeX source on GitHub ----------------------------------------
    "b023": {
        "method": "git",
        "url": "https://github.com/OpenIntroStat/openintro-statistics.git",
        "slug": "openintro_statistics_latex",
        "note": "OpenIntro Statistics. LaTeX source.",
    },
    "b128": {
        "method": "git",
        "url": "https://github.com/OpenLogicProject/OpenLogic.git",
        "slug": "open_logic_project_latex",
        "note": "Open Logic Project. LaTeX source.",
    },
    "b129": {
        "method": "git",
        "url": "https://github.com/rzach/phil210.git",
        "slug": "forallx_calgary_latex",
        "note": "forall x: Calgary. LaTeX source. URL unconfirmed — verify.",
    },

    # --- Jupyter + d2l markdown ----------------------------------------
    "b048": {
        "method": "git",
        "url": "https://github.com/d2l-ai/d2l-en.git",
        "slug": "d2l_en_jupyter",
        "note": "Dive into Deep Learning. Large repo (~1GB). Markdown + Jupyter.",
    },

    # --- Author-posted LaTeX tarballs ----------------------------------
    "b007": {
        "method": "tarball",
        "url": "http://joshua.smcvt.edu/linearalgebra/book.tar.gz",
        "slug": "hefferon_linearalgebra_latex",
        "note": "Hefferon, Linear Algebra. LaTeX source tarball from joshua.smcvt.edu.",
    },

    # --- Documented unavailable ----------------------------------------
    "b081_note": "Stitz-Zeager Precalc: LaTeX source listed in CSV but not clearly on public site; skip for now.",
}


def run_git_clone(url: str, dest: Path) -> dict:
    if dest.exists():
        return {"status": "cached", "path": str(dest.relative_to(OUT_BASE))}
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", str(GIT_DEPTH), url, str(dest)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            return {"status": "fail", "reason": proc.stderr.strip()[-300:]}
        # Verify something came down
        if not any(dest.iterdir()):
            return {"status": "fail", "reason": "clone produced empty dir"}
        return {
            "status": "ok",
            "path": str(dest.relative_to(OUT_BASE)),
            "bytes": sum(p.stat().st_size for p in dest.rglob("*") if p.is_file()),
        }
    except subprocess.TimeoutExpired:
        return {"status": "fail", "reason": "git clone timed out"}
    except Exception as e:
        return {"status": "fail", "reason": str(e)[:300]}


def run_tarball_download(url: str, dest: Path) -> dict:
    if dest.exists():
        return {"status": "cached", "path": str(dest.relative_to(OUT_BASE))}
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.parent / f"{dest.name}.download"
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=120) as r:
            data = r.read()
        archive.write_bytes(data)
        # Detect by magic / suffix
        if url.endswith(".zip") or data[:2] == b"PK":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)
        else:
            with tarfile.open(archive, "r:*") as tf:
                tf.extractall(dest)
        archive.unlink(missing_ok=True)
        return {
            "status": "ok",
            "path": str(dest.relative_to(OUT_BASE)),
            "bytes": sum(p.stat().st_size for p in dest.rglob("*") if p.is_file()),
        }
    except Exception as e:
        archive.unlink(missing_ok=True)
        if dest.exists() and not any(dest.iterdir()):
            dest.rmdir()
        return {"status": "fail", "reason": str(e)[:300]}


def main():
    SRC_DIR.mkdir(parents=True, exist_ok=True)

    # Fail-fast check for git
    if shutil.which("git") is None:
        print("ERROR: git is not installed", file=sys.stderr)
        sys.exit(1)

    # Load CSV for metadata annotation only
    csv_rows = {r["book_id"]: r for r in csv.DictReader(open(CSV_PATH, encoding="utf-8"))}

    results = []
    for bid, spec in SOURCE_MAP.items():
        if bid.endswith("_note") or spec.get("method") == "skip":
            results.append({"book_id": bid, "status": "skip", "reason": spec if isinstance(spec, str) else spec.get("note", "")})
            continue
        slug = spec["slug"]
        dest = SRC_DIR / f"{bid}_{slug}"
        title = csv_rows.get(bid, {}).get("title", "?")

        print(f"[{bid}] fetching via {spec['method']}: {title[:50]}")
        if spec["method"] == "git":
            out = run_git_clone(spec["url"], dest)
        elif spec["method"] == "tarball":
            out = run_tarball_download(spec["url"], dest)
        else:
            out = {"status": "skip", "reason": f"unknown method {spec['method']}"}

        out["book_id"] = bid
        out["title"] = title
        out["url"] = spec.get("url", "")
        out["method"] = spec.get("method", "")
        print(f"       -> {out['status']} {out.get('path') or out.get('reason','')[:100]}")
        results.append(out)

    STATUS_JSON.write_text(json.dumps(results, indent=2))
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    print("\n=== SOURCE SUMMARY ===")
    for k, v in sorted(summary.items()):
        print(f"  {k:10s} {v}")
    total_mb = sum(r.get("bytes", 0) for r in results if r["status"] in ("ok", "cached")) / (1024*1024)
    print(f"  total      {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
