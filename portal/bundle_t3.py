#!/usr/bin/env python3
"""Pack the Tier-3 corpus's per-paper JSONs into one bundle per category and year, so a dataset
host holds thousands of files instead of millions, and the portal still fetches one paper at a
time (an HTTP range request for its bytes).

    portal/bundle_t3.py SRC OUT [--jobs N]   SRC/<cat>/json/<id>.json  ->  OUT/<cat>/<year>.json.xz
                                                                          OUT/<cat>/<year>.idx.json

Format (lossless: unpack() gives back each paper's JSON, equal to the original as JSON):
  - each paper's JSON is written compact (no indentation) and xz-compressed on its own, and the
    papers are written one after another, so a bundle is itself a valid .xz file of all of them;
  - a node's clean_text is left out when it equals the node's statement (it does in every node
    sampled), and unpack() copies statement back into it;
  - the index maps each paper id to [offset, length] in the bundle, or [offset, length, "raw"] for
    a paper stored without the clean_text rule (its JSON is the original, compact);
  - the year comes from the arXiv id (bundle_key), so a reader finds the bundle from the id alone
    and downloads only that bundle's index.
pack() unpacks every paper it writes and stops if one differs from the original.
"""
import argparse
import json
import lzma
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_NEW = re.compile(r"^(\d{2})\d{2}\.\d{4,5}")          # 2403.01234v2
_OLD = re.compile(r"^[a-z\-]+(?:\.[A-Z]{2})?_?(\d{2})\d{2}\d{3}")   # math0306065, math.CO_0306065
# xz level 9 with an 8 MB dictionary (the largest paper sampled is 0.5 MB): within 1% of level 9e,
# 3x faster to write, and a reader needs 9 MB of memory per paper instead of 65
_XZ = [{"id": lzma.FILTER_LZMA2, "preset": 9, "dict_size": 8 << 20}]


def bundle_key(pid: str) -> str:
    """The bundle a paper id goes to: its year 'YYYY' from the arXiv id, else 'other'."""
    m = _NEW.match(pid) or _OLD.match(pid)
    if not m:
        return "other"
    yy = int(m.group(1))
    return str((2000 if yy < 91 else 1900) + yy)


def _dumps(d) -> bytes:
    return json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode()


def unpack(blob: bytes, entry: list) -> dict:
    """A paper's JSON from its bytes in a bundle and its index entry."""
    d = json.loads(lzma.decompress(blob))
    if entry[2:] != ["raw"]:
        for n in d.get("nodes", []):
            if "clean_text" not in n and "statement" in n:
                n["clean_text"] = n["statement"]
    return d


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)   # NaN-safe equality


def _pack_paper(f: Path) -> tuple[bytes, bool]:
    """(the paper's compressed bytes, whether stored raw); checks that unpack() gives it back."""
    orig = json.loads(f.read_bytes())
    d = json.loads(_dumps(orig))
    for n in d.get("nodes", []):
        if "clean_text" in n and n["clean_text"] == n.get("statement"):
            del n["clean_text"]
    blob = lzma.compress(_dumps(d), filters=_XZ)
    if _same(unpack(blob, [0, len(blob)]), orig):
        return blob, False
    blob = lzma.compress(_dumps(orig), filters=_XZ)      # e.g. a node with statement but no clean_text
    if not _same(unpack(blob, [0, len(blob), "raw"]), orig):
        raise SystemExit(f"{f}: unpack() does not give back the original JSON")
    return blob, True


def pack(src: Path, out: Path, jobs: int = 1) -> tuple[int, int, int]:
    """Write every category's bundles and indexes; returns (papers, bundles, papers stored raw)."""
    n_papers = n_bundles = n_raw = 0
    with ProcessPoolExecutor(jobs) as pool:
        for cat_dir in sorted(p for p in src.iterdir() if (p / "json").is_dir()):
            groups = defaultdict(list)
            for f in sorted((cat_dir / "json").glob("*.json")):
                groups[bundle_key(f.stem)].append(f)
            dst = out / cat_dir.name
            dst.mkdir(parents=True, exist_ok=True)
            for key, files in sorted(groups.items()):
                idx, off = {}, 0
                with open(dst / f"{key}.json.xz", "wb") as fh:
                    for f, (blob, raw) in zip(files, pool.map(_pack_paper, files, chunksize=16)):
                        fh.write(blob)
                        idx[f.stem] = [off, len(blob)] + (["raw"] if raw else [])
                        off += len(blob)
                        n_raw += raw
                (dst / f"{key}.idx.json").write_text(json.dumps(idx, separators=(",", ":")))
                n_papers += len(files)
                n_bundles += 1
            print(f"{cat_dir.name}: {sum(map(len, groups.values()))} papers, {len(groups)} bundles",
                  file=sys.stderr, flush=True)
    return n_papers, n_bundles, n_raw


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=1, help="processes compressing papers")
    a = ap.parse_args()
    print("%d papers in %d bundles, %d stored raw (without the clean_text rule)"
          % pack(Path(a.src), Path(a.out), a.jobs))


if __name__ == "__main__":
    main()
