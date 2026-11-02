"""One graph per book from its chapter graphs (v7-books): node ids get the chapter
(`ch06:DP1`), and the links between chapters that each chapter only recorded become edges:

- a `\\ref` to another chapter's label (metadata.unresolved_refs): a `uses` edge, basis `ref`,
  from the labelled node to each node whose statement holds the `\\ref`;
- metadata.book_refs: a `uses` edge (or a mention) from the node it names to the node relying
  on it; a label resolves through the book's label table, a bare name through the earlier
  chapters' definitions and result names;
- metadata.prior_terms: a `uses` edge, basis `term`, from the earliest earlier-chapter
  definition of the term to each node using it.

An edge from a later chapter is kept as a mention (`backward`), since a book is read in order.
The book's labels that are not in it (Open Logic's parts in another prepared book) are looked up
in --also books' label tables and listed in metadata.cross_book_refs.

    python -m structured_math.books.assemble_book BOOK_ID [--also OTHER_ID ...] [--out FILE]
    python -m structured_math.books.assemble_book --all
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
from config import DATASET_ROOT                     # noqa: E402

ROOT = Path(DATASET_ROOT) / "foundation/books_v7b"
_RESULTS = {"theorem", "lemma", "proposition", "corollary", "claim"}
_REF = re.compile(r"\\(?:[cC]?ref|eqref|autoref|nameref)\*?\s*\{([^{}]*)\}")


def norm_term(s: str) -> str:
    """A term as a lookup key: lowercase, no math delimiters, braces or spacing commands,
    no article, singular ("cosets" = "coset")."""
    s = (s or "").lower()
    s = re.sub(r"\\(?:mathbb|mathcal|mathrm|mathbf|operatorname|text|emph|textbf)\s*", "", s)
    s = re.sub(r"[$\\{}~]|\\[,;! ]", " ", s)
    s = re.sub(r"^(?:the|a|an)\s+", "", re.sub(r"\s+", " ", s).strip())
    s = re.sub(r"'s\b", "", s)
    return " ".join(_singular(w) for w in s.split())


_IRREGULAR = {"matrices": "matrix", "vertices": "vertex", "indices": "index", "simplices": "simplex",
              "complexes": "complex", "bases": "basis", "axes": "axis", "hypotheses": "hypothesis"}


def _singular(w: str) -> str:
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) <= 3 or not w.endswith("s") or w.endswith(("ss", "us", "is")):
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "ches", "shes", "xes", "zes")):
        return w[:-2]
    return w[:-1]


def _catalog() -> dict:
    return {b["id"]: b for b in json.loads((HERE / "foundation_books.json").read_text())["books"]}


def book_labels(book_id: str, cat: dict) -> dict:
    """label -> {chapter, ...} of the book's prepared source."""
    p = ROOT / "prepared" / cat[book_id]["prepared"] / "labels.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def assemble(book_id: str, also: list[str] = (), cat: dict | None = None) -> dict:
    cat = cat or _catalog()
    chs = {int(f.stem[2:]): json.loads(f.read_text())
           for f in sorted((ROOT / "graphs" / book_id).glob("ch[0-9][0-9].json"))}
    labels = book_labels(book_id, cat)
    others = {o: book_labels(o, cat) for o in also}
    nid = lambda k, i: f"ch{k:02d}:{i}"                                        # noqa: E731
    nodes, edges, lab2node = [], [], {}
    for k, g in chs.items():
        for n in g["nodes"]:
            m = dict(n, id=nid(k, n["id"]), chapter=k)
            if n.get("parent_id"):
                m["parent_id"] = nid(k, n["parent_id"])
            nodes.append(m)
        edges += [dict(e, source=nid(k, e["source"]), target=nid(k, e["target"])) for e in g["edges"]]
        for lab, v in g["metadata"].get("labels", {}).items():
            node = v.get("node") or v.get("within")
            if node:
                lab2node[lab] = nid(k, node)
    by_id = {n["id"]: n for n in nodes}

    # definitions and named results, for terms and names given without a label
    defined = defaultdict(list)                        # key -> [node id], in reading order
    for n in nodes:
        keys = set()
        if n["type"] == "definition":
            d = n.get("definiendum")
            keys |= {norm_term(x) for x in (d if isinstance(d, list) else [d]) if x}
        if n["type"] in _RESULTS | {"definition"} and n.get("name"):
            keys.add(norm_term(n["name"]))
        for key in keys - {""}:
            defined[key].append(n["id"])
    for v in defined.values():
        v.sort(key=lambda i: (by_id[i]["chapter"], nodes.index(by_id[i])))

    def edge(src: str, tgt: str, basis: str, conf: float, kind: str, note: str) -> dict:
        e = {"source": src, "target": tgt, "type": "uses", "confidence": conf, "basis": basis,
             "cross_chapter": True, "note": note}
        if by_id[src]["chapter"] > by_id[tgt]["chapter"]:
            e["backward"] = e["mention"] = True                   # read later: not relied on
        if kind == "mention":
            e["mention"] = True
        return e

    added, seen = defaultdict(int), {(e["source"], e["target"]) for e in edges}
    unresolved, cross_book = [], []

    def add(e: dict, what: str):
        if e["source"] != e["target"] and (e["source"], e["target"]) not in seen:
            seen.add((e["source"], e["target"]))
            edges.append(e)
            added[what] += 1

    for k, g in chs.items():
        m = g["metadata"]
        # \ref to another chapter's label
        unres = set(m.get("unresolved_refs", []))
        if unres:
            for n in g["nodes"]:
                for lab in set(_REF.findall(n.get("statement", ""))) & unres:
                    for one in (x.strip() for x in lab.split(",")):
                        if one in lab2node:
                            add(edge(lab2node[one], nid(k, n["id"]), "ref", 0.95, "uses", f"\\ref{{{one}}}"), "ref")
                        elif any(one in ol for ol in others.values()):
                            cross_book.append({"node": nid(k, n["id"]), "label": one,
                                               "book": next(o for o, ol in others.items() if one in ol)})
                        elif one in labels:                               # a section or chapter
                            added["ref_to_heading"] += 1
                        else:
                            unresolved.append({"node": nid(k, n["id"]), "label": one})
        # book_refs: a result or definition of another chapter named in words
        for r in m.get("book_refs", []):
            tgt = nid(k, r["node"]) if r.get("node") else None
            if tgt not in by_id:
                continue
            src = lab2node.get(r.get("label") or "")
            if not src:
                cand = [i for i in defined.get(norm_term(r.get("name", "")), []) if by_id[i]["chapter"] != k]
                src = cand[0] if cand else None
            if src:
                add(edge(src, tgt, "named", 0.85, r.get("kind", "uses"), r.get("name", "")), "book_ref")
            elif r.get("label") and any(r["label"] in ol for ol in others.values()):
                cross_book.append({"node": tgt, "label": r["label"], "name": r.get("name")})
            else:
                unresolved.append({"node": tgt, "name": r.get("name"), "label": r.get("label")})
        # prior_terms: the earliest earlier-chapter definition of the term
        for t in m.get("prior_terms", []):
            cand = [i for i in defined.get(norm_term(t["term"]), [])
                    if by_id[i]["chapter"] < k and by_id[i]["type"] == "definition"]
            if not cand:
                unresolved.append({"term": t["term"], "chapter": k})
                continue
            for u in t.get("nodes", []):
                if nid(k, u) in by_id:
                    add(edge(cand[0], nid(k, u), "term", 0.8, "uses", t["term"]), "prior_term")

    b = cat.get(book_id, {})
    meta = {"book_id": book_id, "title": b.get("title"), "topics": b.get("topics", []),
            "license": b.get("license"), "chapters": sorted(chs), "kind": "book",
            "assembled_edges": dict(added), "unresolved": unresolved, "cross_book_refs": cross_book,
            "chapter_metadata": {k: {x: g["metadata"].get(x) for x in
                                     ("title", "prompt_version", "model", "extraction_date", "paper_style")}
                                 for k, g in chs.items()}}
    return {"metadata": meta, "nodes": nodes, "edges": edges}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("book", nargs="?")
    ap.add_argument("--also", nargs="*", default=[], help="books whose labels this one may cite (Open Logic parts)")
    ap.add_argument("--all", action="store_true", help="every book with extracted chapters")
    ap.add_argument("--out", help="default: <ROOT>/assembled/<book>.json")
    a = ap.parse_args()
    cat = _catalog()
    books = [d.name for d in sorted((ROOT / "graphs").iterdir())
             if d.is_dir() and d.name in cat and any(d.glob("ch[0-9][0-9].json"))] if a.all else [a.book]
    # the Open Logic books cite each other's labels
    pairs = {"b128_openlogic": ["b200_slc"], "b200_slc": ["b128_openlogic"]}
    for bk in books:
        g = assemble(bk, a.also or pairs.get(bk, []), cat)
        out = Path(a.out) if a.out and not a.all else ROOT / "assembled" / f"{bk}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(g, ensure_ascii=False))
        m = g["metadata"]
        print(f"{bk:22} {len(m['chapters']):3d} ch {len(g['nodes']):6d} nodes {len(g['edges']):6d} edges  "
              f"added {m['assembled_edges']}  unresolved {len(m['unresolved'])}  cross-book {len(m['cross_book_refs'])}")


if __name__ == "__main__":
    main()
