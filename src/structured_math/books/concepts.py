"""The concept layer of the foundation from the assembled books (assemble_book.py): one concept
per notion, merged across books, with prerequisite edges between concepts.

A concept is a defined term (each definiendum of a definition node) or a main named result.
Nodes with the same term key (assemble_book.norm_term) are one concept when they come from the
same book (and the same `sense`, which a reference source such as ProofWiki gives to its pages
"Ring (Abstract Algebra)" and "Ring (Set Theory)"), carry the same name or genus, or their
statements share enough content words; a term
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
# a result's title that is a name ("Hall's theorem", "Banach fixed point theorem"), not a label
# for it (Beezer's "Four Subsets"); a statement-title ("Union is Associative") is not one either
RESULT_NAME = re.compile(r"(?i)\b(theorem|lemma|inequality|formula|principle|law|conjecture|identity|criterion)\b")


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
    reference = {g["metadata"]["book_id"] for g in books if g["metadata"].get("kind") == "reference"}
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
                                                 "sense": n.get("sense"),
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
                same = ((x["book"] == y["book"] and x["sense"] == y["sense"])
                        or (x["name"] and norm_term(x["name"]) == norm_term(y["name"]))
                        or (x["genus"] and x["genus"] == y["genus"])
                        or jaccard(x["words"], y["words"]) >= min_sim)
                if same:
                    uf.union(a, b)
        # a reference source's page for the term itself (no sense: ProofWiki's "Group") is the
        # term's common meaning: it joins the books' concept when the books have only one
        ref = [k for k in ks if items[k]["book"] in reference and items[k]["sense"] is None]
        rest = {uf.find(k) for k in ks if items[k]["book"] not in reference}
        if ref and len(rest) == 1:
            for k in ref:
                uf.union(k, next(iter(rest)))
    groups = defaultdict(list)
    for k in items:
        groups[uf.find(k)].append(k)
    concepts, member_of = [], defaultdict(set)          # (book, node) -> concept ids
    for root, ks in sorted(groups.items(), key=lambda kv: (items[kv[0]]["key"], -len(kv[1]))):
        key = items[ks[0]]["key"]
        # the name that is the term itself, then a book's name before a reference page's
        # ("Topological space", not "Open Set/Topology"), then the shortest
        names = sorted({items[k]["name"] for k in ks if items[k]["name"]},
                       key=lambda x: (norm_term(x) != key,
                                      all(items[k]["book"] in reference for k in ks if items[k]["name"] == x), len(x)))
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


_SYMBOLS = {"emptyset": "empty set", "varnothing": "empty set", "mathbb n": "natural number",
            "mathbb z": "integer", "mathbb q": "rational number", "mathbb r": "real number",
            "mathbb c": "complex number"}


def stem(key: str) -> str:
    """A rough stem for spotting word-form variants: bijection / bijective / bijectivity."""
    key = _SYMBOLS.get(key, key)
    return " ".join(re.sub(r"(?:ization|isation|ivity|ation|ition|ness|ence|ance|ity|ive|ion|ing|al|ic|ed)$", "", w)
                    for w in key.split())


def candidates(g: dict) -> list[dict]:
    """Groups of concepts an LLM should look at: one term split into several concepts, and
    concepts whose terms differ only by word form or symbol. Each group lists its concepts
    with up to two member statements."""
    by_stem = defaultdict(list)
    for c in g["concepts"]:
        by_stem[stem(c["term"])].append(c)
    out = []
    for st, cs in sorted(by_stem.items()):
        if len(cs) < 2:
            continue
        out.append({"group": st, "concepts": [
            {"id": c["id"], "term": c["term"], "name": c["name"], "books": c["books"],
             "statements": [m["statement"][:220] for m in c["members"][:2]]} for c in cs]})
    return out


def member_refs(g: dict, merges: list[list[str]]) -> list[list[str]]:
    """Merge lists of concept ids of the build `g` as stable member refs "book:node:term" (each
    concept by its first member), so they still apply after the concepts are rebuilt."""
    C = {c["id"]: c for c in g["concepts"]}
    ref = lambda m: f'{m["book"]}:{m["node"]}:{norm_term(m["term"])}'     # noqa: E731
    return [[ref(C[i]["members"][0]) for i in ids if i in C] for ids in merges]


def merge(g: dict, merges: list[list[str]]) -> dict:
    """Merge the listed concepts (each list becomes its first concept), named by concept id or,
    stable across rebuilds, by a member "book:node:term"; edges are remapped and their book
    sets joined."""
    C = {c["id"]: c for c in g["concepts"]}
    by_member = {f'{m["book"]}:{m["node"]}:{norm_term(m["term"])}': c["id"] for c in g["concepts"] for m in c["members"]}
    to = {}
    for ids in merges:                       # concept ids, or stable member refs "book:node:term"
        ids = list(dict.fromkeys(by_member.get(i, i) for i in ids))
        ids = [i for i in ids if i in C and i not in to]
        for i in ids[1:]:
            to[i] = ids[0]
            C[ids[0]]["members"] += C[i]["members"]
            C[ids[0]]["books"] = sorted(set(C[ids[0]]["books"]) | set(C[i]["books"]))
            C[ids[0]].setdefault("aliases", []).append(C[i]["term"])
    g["concepts"] = [c for c in g["concepts"] if c["id"] not in to]
    pre = defaultdict(set)
    for e in g["edges"]:
        a, b = to.get(e["source"], e["source"]), to.get(e["target"], e["target"])
        if a != b:
            pre[(a, b)] |= set(e["books"])
    g["edges"] = [{"source": a, "target": b, "type": "prerequisite", "books": sorted(bs), "n_books": len(bs)}
                  for (a, b), bs in sorted(pre.items())]
    terms = defaultdict(list)
    for c in g["concepts"]:
        terms[c["term"]].append(c["id"])
    g["homonyms"] = {t: ids for t, ids in terms.items() if len(ids) > 1}
    g["metadata"].update(concepts=len(g["concepts"]), multi_book=sum(len(c["books"]) > 1 for c in g["concepts"]),
                         homonym_terms=len(g["homonyms"]), edges=len(g["edges"]), merged=len(to))
    return g


_HEADING = re.compile(r"=+[^=]*=+")


def prune_stubs(g: dict) -> dict:
    """Drop members whose statement holds no text: a ProofWiki page that only transcludes its
    sub-definitions ("=== Definition 1 === === Definition 2 ==="). Ids and books are kept, so a
    grounding layer built on the concepts stays valid."""
    n = 0
    for c in g["concepts"]:
        keep = [m for m in c["members"] if re.search(r"[A-Za-z]{3}", _HEADING.sub("", m.get("statement") or ""))]
        n += len(c["members"]) - len(keep)
        c["members"] = keep
    g["metadata"]["stub_members_pruned"] = g["metadata"].get("stub_members_pruned", 0) + n
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "concepts.json"))
    ap.add_argument("--prune-stubs", metavar="CONCEPTS", help="drop text-less members from this concepts.json in place (a .bak is kept)")
    ap.add_argument("--min-sim", type=float, default=0.2)
    ap.add_argument("--candidates", help="write the groups for an LLM to judge to this file")
    ap.add_argument("--merges", help="a JSON list of concept-id lists to merge (the LLM's judgments)")
    a = ap.parse_args()
    if a.prune_stubs:
        f = Path(a.prune_stubs)
        g = json.loads(f.read_text(encoding="utf-8"))
        before = sum(len(c["members"]) for c in g["concepts"])
        g = prune_stubs(g)
        f.with_suffix(".json.bak").write_bytes(f.read_bytes())
        f.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
        print(before - sum(len(c["members"]) for c in g["concepts"]), "stub members dropped ->", f)
        return
    books = [json.loads(f.read_text()) for f in sorted((ROOT / "assembled").glob("*.json"))]
    g = build(books, a.min_sim)
    if a.merges:
        g = merge(g, json.loads(Path(a.merges).read_text()))
    if a.candidates:
        cand = candidates(g)
        Path(a.candidates).write_text(json.dumps(cand, ensure_ascii=False, indent=1))
        print(len(cand), "candidate groups ->", a.candidates)
    Path(a.out).write_text(json.dumps(g, ensure_ascii=False))
    print(json.dumps(g["metadata"]), "->", a.out)


if __name__ == "__main__":
    main()
