#!/usr/bin/env python3
"""Pack the Tier-3 corpus's per-paper JSONs into one bundle per category and month, so a
dataset host holds thousands of files instead of millions, and the portal still fetches one
paper at a time (an HTTP range request for its bytes).

    portal/bundle_t3.py SRC OUT      SRC/<cat>/json/<id>.json  ->  OUT/<cat>/<month>.json.gz
                                                                   OUT/<cat>/<month>.idx.json

A bundle is the papers' JSONs, each gzipped on its own and written one after another (so a
bundle is itself a valid gzip file of all of them). Its index maps each paper id to
[offset, length] in the bundle. The month comes from the arXiv id (bundle_month), so the
portal finds the bundle from the id alone and downloads only that month's small index.
"""
import argparse
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_NEW = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}")          # 2403.01234v2
_OLD = re.compile(r"^[a-z\-]+(?:\.[A-Z]{2})?_?(\d{2})(\d{2})\d{3}")   # math0306065, math.CO_0306065


def bundle_month(pid: str) -> str:
    """The bundle a paper id goes to: 'YYYY-MM' from the arXiv id, else 'other'."""
    m = _NEW.match(pid) or _OLD.match(pid)
    if not m:
        return "other"
    yy, mm = int(m.group(1)), m.group(2)
    return f"{(2000 if yy < 91 else 1900) + yy}-{mm}"


def pack(src: Path, out: Path) -> tuple[int, int]:
    """Write every category's bundles and indexes; returns (papers, bundles)."""
    n_papers = n_bundles = 0
    for cat_dir in sorted(p for p in src.iterdir() if (p / "json").is_dir()):
        months = defaultdict(list)
        for f in sorted((cat_dir / "json").glob("*.json")):
            months[bundle_month(f.stem)].append(f)
        dst = out / cat_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        for month, files in sorted(months.items()):
            idx, off = {}, 0
            with open(dst / f"{month}.json.gz", "wb") as fh:
                for f in files:
                    blob = gzip.compress(f.read_bytes(), compresslevel=9, mtime=0)
                    fh.write(blob)
                    idx[f.stem] = [off, len(blob)]
                    off += len(blob)
            (dst / f"{month}.idx.json").write_text(json.dumps(idx, separators=(",", ":")))
            n_papers += len(files)
            n_bundles += 1
        print(f"{cat_dir.name}: {sum(map(len, months.values()))} papers, {len(months)} bundles", file=sys.stderr)
    return n_papers, n_bundles


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("out")
    a = ap.parse_args()
    print("%d papers in %d bundles" % pack(Path(a.src), Path(a.out)))


if __name__ == "__main__":
    main()
