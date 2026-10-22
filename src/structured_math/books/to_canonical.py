"""Bring the extracted textbooks to the current canonical schema (src/node_types.py,
src/edge_types.py), the one the v7 papers use. No LLM calls.

Two inputs:
  * the 105 books migrate_to_unified.py already converted
    (<DATA_DIR>/foundation/books/<book>/<chapter>.unified.json);
  * the books it could not read (their chapters keep nodes under `nodes` or `items`,
    edges inside each node, `title`/`content` for name/text), read here from
    textbooks/extracted/<book>/.

What changes:
  * Edge direction. The books write "A uses B" for "A depends on B" (57 of 59 books
    whose uses-edges touch a definition point from the result to the definition); the
    canonical arrow is A -> B for "B depends on A". uses, mentions_concept, generalizes,
    specializes and solves are flipped; proves (proof -> result) already agrees.
  * Edge types. mentions_concept becomes tests (into an exercise), illustrates (into
    an example) or uses; solves becomes resolves (problem -> algorithm);
    special_case_of edges, which the migration turned into generalizes, become
    specializes; has_part becomes the part's parent_id; related_to is dropped.
  * Node types. theorem_like, named_result -> theorem; construction,
    concept_article -> definition; axiom -> assumption. The book's own word is kept
    in `display`.
  * Fields. statement (verbatim LaTeX, from raw_latex), statement_short (the book's
    clean text, when it differs), section (the chapter title), origin "paper" (the
    book's own content), confidence (1.0 for a numbered environment, else 0.8), and
    label / page / tags kept.

    python -m structured_math.books.to_canonical              # all books
    python -m structured_math.books.to_canonical --book b006_axler
Output: <DATA_DIR>/foundation/books_canonical/<book>/<chapter>.json and summary.json.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config import DATA_DIR                      # noqa: E402
import edge_types as ET                          # noqa: E402
import node_types as NT                          # noqa: E402

MIGRATED = DATA_DIR / "foundation" / "books"
EXTRACTED = _SRC.parent / "textbooks" / "extracted"
OUT = DATA_DIR / "foundation" / "books_canonical"

NODE_TYPES = {getattr(NT, k) for k in dir(NT) if k.isupper() and isinstance(getattr(NT, k), str)
              and getattr(NT, k) in NT.SUBCLASS_VALUES} | {NT.ASSUMPTION}
TYPE_MAP = {"theorem_like": NT.THEOREM, "named_result": NT.THEOREM, "construction": NT.DEFINITION,
            "concept_article": NT.DEFINITION, "axiom": NT.ASSUMPTION}
FLIP = {"uses", "mentions_concept", "generalizes", "specializes", "solves", "illustrates",
        "depends_on", "follows_from"}
SKIP_FILES = ("book.json", "progress.json", "status.json", "toc.json")


def _meta(m) -> dict:
    if isinstance(m, dict):
        return m
    if isinstance(m, str):
        try:
            v = ast.literal_eval(m)
            return v if isinstance(v, dict) else {}
        except (ValueError, SyntaxError):
            return {}
    return {}


def node(n: dict, section: str) -> dict | None:
    nid = n.get("id") or n.get("node_id")
    if not nid:
        return None
    word = str(n.get("type") or "").strip().lower()
    t = TYPE_MAP.get(word, NT.normalize_node_type(word) if word else NT.REMARK)
    if t not in NODE_TYPES:
        t = NT.REMARK
    raw = (n.get("raw_latex") or n.get("statement_latex") or n.get("statement") or n.get("content")
           or n.get("raw_text") or n.get("clean_text") or "").strip()
    clean = (n.get("clean_text") or n.get("statement_clean") or "").strip()
    name = (n.get("name") or n.get("title") or "").strip()
    label = n.get("label")
    label = None if label in (None, "", "None") else str(label)
    out = {"id": nid, "type": t, "name": name or label or nid, "statement": raw or name,
           "section": section, "origin": NT.ORIGIN_PAPER, "confidence": 1.0 if label else 0.8}
    if clean and clean != raw:
        out["statement_short"] = clean
    if word and word != t:
        out["display"] = word
    if label:
        out["label"] = label
    md = _meta(n.get("metadata"))
    for k in ("page", "tags", "subclass"):
        v = n.get(k, md.get(k))
        if v not in (None, "", []):
            out[k] = v
    if out.get("subclass") not in NT.SUBCLASS_VALUES.get(t, ()):
        out.pop("subclass", None)
    for src, dst in (("assumptions", "assumptions"), ("assumptions_latex", "assumptions"),
                     ("conclusions", "conclusions"), ("conclusions_latex", "conclusions")):
        if isinstance(n.get(src), list) and n[src] and dst not in out:
            out[dst] = n[src]
    return out


def edge(s: str, t: str, kind: str, nodes: dict, remap=(), stats=None) -> tuple | None:
    """A book edge (s, t, kind) as a canonical (source, target, type), or None to drop."""
    kind = (kind or "uses").lower()
    if "flipped(special_case_of)" in remap:   # the migration already flipped it: A -> B, B special case of A
        return (s, t, ET.SPECIALIZES)
    if kind == "special_case_of":             # s special case of t: t -> s, s specializes t
        return (t, s, ET.SPECIALIZES)
    if kind in ("related_to", "equivalent_to", "tests", "has_part", "contains_named_result"):
        return None
    if kind == "proves":
        return (s, t, ET.PROVES)
    if kind not in FLIP:
        stats["unknown_edge:" + kind] += 1
        return None
    a, b = t, s                               # flipped: the prerequisite first
    if kind == "solves":                      # algorithm solves problem: problem -> algorithm
        return (a, b, ET.RESOLVES)
    if kind in ("generalizes", "specializes"):
        return (a, b, kind)
    dep = nodes.get(b, {}).get("type")
    if kind in ("mentions_concept", "illustrates") and dep == NT.EXERCISE:
        return (a, b, ET.TESTS)
    if kind in ("mentions_concept", "illustrates") and dep == NT.EXAMPLE:
        return (a, b, ET.ILLUSTRATES)
    return (a, b, ET.USES)


def chapter(raw_nodes: list, raw_edges: list, meta: dict, stats: Counter) -> dict:
    """raw_edges: (source, target, kind, remap) in the book's convention."""
    section = str(meta.get("chapter_title") or meta.get("title") or "")
    nodes = {}
    for n in raw_nodes:
        c = node(n, section) if isinstance(n, dict) else None
        if c and c["id"] not in nodes:
            nodes[c["id"]] = c
    edges, seen = [], set()
    for s, t, kind, remap in raw_edges:
        if kind == "has_part" and t in nodes and s in nodes:
            nodes[t]["parent_id"] = s
            continue
        if s not in nodes or t not in nodes or s == t:
            stats["edges_dangling"] += 1
            continue
        e = edge(s, t, kind, nodes, remap, stats)
        if e is None:
            stats["edges_dropped:" + kind] += 1
        elif e not in seen:
            seen.add(e)
            edges.append({"source": e[0], "target": e[1], "type": e[2]})
            stats["edge:" + e[2]] += 1
    for n in nodes.values():
        stats["node:" + n["type"]] += 1
    return {"metadata": {**meta, "source": "book", "schema": "canonical (to_canonical.py)"},
            "nodes": list(nodes.values()), "edges": edges}


def from_migrated(book: Path, stats: Counter):
    for f in sorted(book.glob("*.unified.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        ed = [(e["source"], e["target"], e["type"], tuple(e.get("_remap") or ())) for e in d["edges"]]
        yield f.name.replace(".unified.json", ""), chapter(d["nodes"], ed, d.get("metadata") or {}, stats)


def from_extracted(book: Path, stats: Counter):
    for f in sorted(book.rglob("*.json")):
        if f.name in SKIP_FILES or "summary" in f.name or "progress" in f.name or "failed" in f.name:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stats["files_unreadable"] += 1
            continue
        raw = d.get("nodes") if isinstance(d, dict) else None
        raw = raw if isinstance(raw, list) else (d.get("items") if isinstance(d, dict) else None)
        if not isinstance(raw, list) or not raw:
            continue
        ed = []
        for n in raw:
            nid = isinstance(n, dict) and (n.get("id") or n.get("node_id"))
            for e in (n.get("edges") or []) if nid and isinstance(n.get("edges"), list) else []:
                if isinstance(e, dict) and e.get("target"):
                    ed.append((nid, e["target"], e.get("type") or e.get("relation"), ()))
            for k in ("uses", "illustrates", "special_case_of"):
                for t in (n.get(k) or []) if nid and isinstance(n.get(k), list) else []:
                    ed.append((nid, t, k, ()))
        for e in d["edges"] if isinstance(d.get("edges"), list) else []:
            if not isinstance(e, dict):
                continue
            s, t = e.get("source") or e.get("from") or e.get("src"), e.get("target") or e.get("to") or e.get("dst")
            ed.append((s, t, e.get("type") or e.get("relation"), ()))
        meta = {k: d.get(k) for k in ("book_id", "chapter_id", "chapter_title", "title") if d.get(k)}
        yield f.relative_to(book).with_suffix("").as_posix().replace("/", "__"), chapter(raw, ed, meta, stats)


def convert(book_id: str, out: Path) -> Counter:
    stats = Counter()
    mig = MIGRATED / book_id
    src = from_migrated(mig, stats) if list(mig.glob("*.unified.json")) else from_extracted(EXTRACTED / book_id, stats)
    for name, ch in src:
        if not ch["nodes"]:
            continue
        (out / book_id).mkdir(parents=True, exist_ok=True)
        (out / book_id / f"{name}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["chapters"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--book")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    books = [a.book] if a.book else sorted({p.name for p in MIGRATED.iterdir() if p.is_dir()}
                                           | {p.name for p in EXTRACTED.iterdir() if p.is_dir()})
    total, per = Counter(), {}
    for b in books:
        s = convert(b, out)
        if s["chapters"]:
            per[b] = {"chapters": s["chapters"], "nodes": sum(v for k, v in s.items() if k.startswith("node:")),
                      "edges": sum(v for k, v in s.items() if k.startswith("edge:"))}
        total.update(s)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"books": per, "totals": dict(sorted(total.items()))}, indent=1))
    print(f"{len(per)} books, {total['chapters']} chapters, "
          f"{sum(p['nodes'] for p in per.values())} nodes, {sum(p['edges'] for p in per.values())} edges -> {out}")
    for k, v in sorted(total.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
