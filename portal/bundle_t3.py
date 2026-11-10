#!/usr/bin/env python3
"""Pack the Tier-3 corpus's per-paper JSONs into one bundle per category and year, so a dataset
host holds thousands of files instead of millions, and the portal still fetches one paper at a
time (an HTTP range request for its bytes).

    portal/bundle_t3.py SRC OUT [--jobs N]   SRC/<cat>/json/<id>.json  ->  OUT/<cat>/<year>.json.xz
                                                                          OUT/<cat>/<year>.idx.json
    SRC may also be a bundle folder (OUT of an earlier run): its papers are unpacked and repacked.

    --grounding DIR --concepts FILE   copy the book grounding (ground_papers output, DIR/<cat>.jsonl)
        into each paper: its grounded_to edges from the old name linker are dropped and the layer's
        edges (node -> concept id, with term, basis, confidence) are written in, each with the
        concept's name, kind and books from concepts.json, so the paper reads on its own. The
        layer stays the canonical grounding; this is how the portal (and anyone reading a paper
        alone) gets it.

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


_GROUNDING = {}      # per process: paper id -> the layer's edges (set by _init_grounding)
_CONCEPTS = {}       # concept id -> {name, kind, books}
_OLD_ID = re.compile(r"^([a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2,3})?)_(\d{7}(?:v\d+)?)$")


def paper_key(stem: str) -> str:
    """The arXiv id the grounding layer keys a paper by: no _rules/_manual suffix, no version,
    old ids with their slash (math_0306065v1 -> math/0306065)."""
    k = re.sub(r"_(rules|manual|llm|anthropic|openai)$", "", stem)
    m = _OLD_ID.match(k)
    if m:
        k = f"{m.group(1)}/{m.group(2)}"
    return re.sub(r"v\d+$", "", k)


def load_grounding(grounding: Path, concepts: Path) -> tuple[dict, dict]:
    """The layer's edges per paper id, and the concept records the edges point to."""
    g = {}
    for jl in sorted(Path(grounding).glob("*.jsonl")):
        with open(jl, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    if row.get("edges"):
                        g[row["paper_id"]] = row["edges"]
    need = {e["target"] for es in g.values() for e in es}
    c = {}
    for rec in json.loads(Path(concepts).read_text(encoding="utf-8")).get("concepts", []):
        if rec["id"] in need:
            c[rec["id"]] = {"name": rec.get("name") or rec["id"], "kind": rec.get("kind", ""),
                            "books": rec.get("books", [])}
    return g, c


def _init_grounding(g, c):
    global _GROUNDING, _CONCEPTS
    _GROUNDING, _CONCEPTS = g, c


def with_grounding(d: dict, stem: str) -> dict:
    """The paper with the layer's grounding edges in place of the old name-linker ones."""
    edges = [e for e in d.get("edges", []) if e.get("type") != "grounded_to"]
    for e in _GROUNDING.get(paper_key(stem), []):
        c = _CONCEPTS.get(e["target"], {})
        edges.append({**e, "concept_name": c.get("name", e["target"]), "concept_kind": c.get("kind", ""),
                      "concept_books": c.get("books", [])})
    d["edges"] = edges
    return d


def _load(f) -> tuple[str, dict]:
    """(stem, JSON) of a source paper: a file, or (bundle, index entry, stem) of a packed one."""
    if isinstance(f, Path):
        return f.stem, json.loads(f.read_bytes())
    bundle, entry, stem = f
    with open(bundle, "rb") as fh:
        fh.seek(entry[0])
        return stem, unpack(fh.read(entry[1]), entry)


def _pack_paper(f) -> tuple[bytes, bool]:
    """(the paper's compressed bytes, whether stored raw); checks that unpack() gives it back."""
    stem, orig = _load(f)
    if _GROUNDING:
        orig = with_grounding(orig, stem)
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


def _sources(cat_dir: Path) -> list:
    """What _load takes, per paper of a category: files under json/, or the entries of its bundles."""
    if (cat_dir / "json").is_dir():
        return sorted((cat_dir / "json").glob("*.json"))
    srcs = []
    for b in sorted(cat_dir.glob("*.json.xz")):
        idx = json.loads(Path(str(b)[:-8] + ".idx.json").read_text())
        srcs += [(b, entry, stem) for stem, entry in idx.items()]
    return srcs


def _stem(f) -> str:
    return f.stem if isinstance(f, Path) else f[2]


def pack(src: Path, out: Path, jobs: int = 1, grounding: Path = None, concepts: Path = None) -> tuple[int, int, int]:
    """Write every category's bundles and indexes; returns (papers, bundles, papers stored raw)."""
    n_papers = n_bundles = n_raw = 0
    g, c = load_grounding(grounding, concepts) if grounding else ({}, {})
    if grounding:
        print(f"grounding: {len(g)} papers, {len(c)} concepts", file=sys.stderr, flush=True)
    with ProcessPoolExecutor(jobs, initializer=_init_grounding, initargs=(g, c)) as pool:
        for cat_dir in sorted(p for p in src.iterdir() if (p / "json").is_dir() or list(p.glob("*.idx.json"))):
            groups = defaultdict(list)
            for f in _sources(cat_dir):
                groups[bundle_key(_stem(f))].append(f)
            dst = out / cat_dir.name
            dst.mkdir(parents=True, exist_ok=True)
            for key, files in sorted(groups.items()):
                idx, off = {}, 0
                with open(dst / f"{key}.json.xz", "wb") as fh:
                    for f, (blob, raw) in zip(files, pool.map(_pack_paper, files, chunksize=16)):
                        fh.write(blob)
                        idx[_stem(f)] = [off, len(blob)] + (["raw"] if raw else [])
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
    ap.add_argument("--grounding", default=None, help="ground_papers output folder (<cat>.jsonl): copy its edges in")
    ap.add_argument("--concepts", default=None, help="the concepts.json the grounding was made with")
    a = ap.parse_args()
    if bool(a.grounding) != bool(a.concepts):
        ap.error("--grounding and --concepts go together")
    if a.grounding and Path(a.src).resolve() == Path(a.out).resolve():
        ap.error("OUT must differ from SRC")
    print("%d papers in %d bundles, %d stored raw (without the clean_text rule)"
          % pack(Path(a.src), Path(a.out), a.jobs, a.grounding and Path(a.grounding), a.concepts and Path(a.concepts)))


if __name__ == "__main__":
    main()
