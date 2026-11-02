"""The concept layer of the foundation from the assembled books (assemble_book.py): one concept
per notion, merged across books, with prerequisite edges between concepts.

A concept is a defined term (each definiendum of a definition node) or a main named result.
Nodes with the same term key (assemble_book.norm_term) are one concept when they come from the
same book, carry the same name or genus, or their statements share enough content words; a term
whose nodes split into several concepts is a homonym ("complete": graph, theory). An edge
A -> B between book nodes (uses, specializes, generalizes; not mentions) becomes a prerequisite
edge between their concepts, with the books that state it.

    python -m structured_math.books.concepts [--out FILE] [--min-sim 0.2]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from structured_math.books.assemble_book import ROOT, norm_term      # noqa: E402

_STOP = set("a an the of and or to in on for is are be by with that this which it its as at if then "
            "we let such any every each some all there from into called said say define defined denote "
            "write where when not no".split())
_PREREQ = {"uses", "specializes", "generalizes"}


def words(s: str) -> set:
    s = re.sub(r"\$[^$]*\$|\\\[.*?\\\]|\\[A-Za-z]+|[{}]", " ", s or "", flags=re.S).lower()
    return {w for w in re.findall(r"[a-z]{3,}", s) if w not in _STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def build(books: list[dict], min_sim: float = 0.2) -> dict:
    items = {}                                         # (book, node id, term) -> info
    for g in books:
        bk = g["metadata"]["book_id"]
        for n in g["nodes"]:
            terms = []
            if n["type"] == "definition":
                d = n.get("definiendum")
                terms = [t for t in (d if isinstance(d, list) else [d]) if t]
            elif n.get("main") and n.get("name"):
                terms = [n["name"]]
            for t in terms:
                key = norm_term(t)
                if len(key) >= 2:
                    items[(bk, n["id"], key)] = {"book": bk, "node": n["id"], "term": t, "key": key,
                                                 "type": n["type"], "name": n.get("name") or "",
                                                 "genus": norm_term(n.get("genus") or ""),
                                                 "words": words(n.get("statement", "")),
                                                 "statement": (n.get("statement") or "")[:300]}
    by_key = defaultdict(list)
    for k, v in items.items():
        by_key[v["key"]].append(k)
    uf = _UF()
    for key, ks in by_key.items():
        for i, a in enumerate(ks):
            uf.find(a)
            for b in ks[i + 1:]:
                x, y = items[a], items[b]
                same = (x["book"] == y["book"]
                        or (x["name"] and norm_term(x["name"]) == norm_term(y["name"]))
                        or (x["genus"] and x["genus"] == y["genus"])
                        or jaccard(x["words"], y["words"]) >= min_sim)
                if same:
                    uf.union(a, b)
    groups = defaultdict(list)
    for k in items:
        groups[uf.find(k)].append(k)
    concepts, member_of = [], defaultdict(set)          # (book, node) -> concept ids
    for root, ks in sorted(groups.items(), key=lambda kv: (items[kv[0]]["key"], -len(kv[1]))):
        key = items[ks[0]]["key"]
        names = sorted({items[k]["name"] for k in ks if items[k]["name"]}, key=len)
        cid = f"C{len(concepts) + 1}"
        concepts.append({"id": cid, "term": key, "name": names[0] if names else items[ks[0]]["term"],
                         "kind": "result" if all(items[k]["type"] != "definition" for k in ks) else "definition",
                         "books": sorted({items[k]["book"] for k in ks}),
                         "members": [{x: items[k][x] for x in ("book", "node", "term", "name", "statement")}
                                     for k in ks]})
        for k in ks:
            member_of[(items[k]["book"], items[k]["node"])].add(cid)
    homonyms = defaultdict(list)
    for c in concepts:
        homonyms[c["term"]].append(c["id"])
    homonyms = {t: ids for t, ids in homonyms.items() if len(ids) > 1}
    # prerequisites: book edges between concept nodes
    pre = defaultdict(set)
    for g in books:
        bk = g["metadata"]["book_id"]
        for e in g["edges"]:
            if e["type"] not in _PREREQ or e.get("mention"):
                continue
            for a in member_of.get((bk, e["source"]), ()):
                for b in member_of.get((bk, e["target"]), ()):
                    if a != b:
                        pre[(a, b)].add(bk)
    edges = [{"source": a, "target": b, "type": "prerequisite", "books": sorted(bs), "n_books": len(bs)}
             for (a, b), bs in sorted(pre.items())]
    return {"metadata": {"books": [g["metadata"]["book_id"] for g in books], "min_sim": min_sim,
                         "concepts": len(concepts), "multi_book": sum(len(c["books"]) > 1 for c in concepts),
                         "homonym_terms": len(homonyms), "edges": len(edges)},
            "concepts": concepts, "edges": edges, "homonyms": homonyms}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "concepts.json"))
    ap.add_argument("--min-sim", type=float, default=0.2)
    a = ap.parse_args()
    books = [json.loads(f.read_text()) for f in sorted((ROOT / "assembled").glob("*.json"))]
    g = build(books, a.min_sim)
    Path(a.out).write_text(json.dumps(g, ensure_ascii=False))
    print(json.dumps(g["metadata"]), "->", a.out)


if __name__ == "__main__":
    main()
