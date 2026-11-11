"""Ground paper graphs in the book concept layer (concepts.py): a `grounded_to` edge from a paper
node to the book concept whose term it uses, written as a separate layer so the paper graphs are
untouched.

A concept is found by its term or an alias (assemble_book.norm_term on words, the longest match
winning: "complete graph" before "graph"), in the node's text with math, macros and citations
removed; a named result by its name. A term in more than --max-df of the papers ("set",
"function", "union") is common vocabulary and is not grounded. A term shared by several concepts
(a homonym: "complete" graph / theory / metric space) goes to the concept whose book statements
share most words with the paper; when no concept is clearly closer the occurrence is dropped. A
paper definition of the term itself (the term in its \\emph / \\textbf / \\textit) is basis
"defines": the paper restates or redefines a standard notion.

    python -m structured_math.books.ground_papers ROOT [--out DIR] [--categories math_CO ...] [--jobs 8]

ROOT holds the paper graphs (corpus_io layout or bundles). OUT gets <category>.jsonl, one line per
paper with grounding edges ({paper_id, edges}), and summary.json.

The full-arXiv parse (ROOT/YYYY/MM/DD.tar.gz, a category per paper from an id table) runs as one
task per year, then one pooling step, so the common-vocabulary cut sees the whole corpus:

    python -m structured_math.books.ground_papers ROOT --out DIR --cats cats.tsv.gz --years 2019 --scan-only 2019
    ...                                                                     (one per year, a SLURM array)
    python -m structured_math.books.ground_papers --out DIR --finalize
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[1] / "discovery" / "common"))
from structured_math.books.assemble_book import ROOT, norm_term      # noqa: E402
from structured_math.books.concepts import RESULT_NAME, words         # noqa: E402

_GENERIC = set("theorem lemma proposition corollary definition proof example remark claim exercise "
               "problem conjecture equation algorithm section chapter case step result notation".split()) | {
    "well defined", "well-defined", "uniquely determined", "if and only if", "such that",
    "without loss of generality", "left hand", "right hand", "left hand side", "right hand side",
    "last term", "less than or equal", "greater than or equal", "sufficient condition", "necessary condition",
    "first order", "second order", "infinite length", "finite length",
    # how a text argues, not what it is about (a proof "by contradiction" does not rest on the concept)
    "direct proof", "indirect proof", "proof by contradiction", "proof by induction", "proof by cases",
    "mathematical induction", "strong induction", "induction hypothesis", "inductive step", "base case",
    "contrapositive", "contradiction", "counterexample", "constructive proof", "existence proof",
    "uniqueness proof", "argument", "statement", "conditional statement", "hypothesis", "conclusion",
    "assumption", "axiom", "notation", "proof technique"}
_ROMAN = {"i", "ii", "iii", "iv", "v", "vi"}            # "type II" (a domain in one book, a tail in a paper)
_MAX_N = 6                                     # longest term, in words
_EDGE_WORDS = set("of from to at in on by for with and or the a an between under over into onto than "
                  "is are".split())                       # "path from $u$ to $v$", "distance between"
_ALL = "*"
# the arXiv categories where a book topic's one-word terms keep their meaning ("cell": a memory
# cell in Open Data Structures, not a cell of a complex); multi-word terms are not restricted
_MATH = {"math_AG", "math_AP", "math_AT", "math_CA", "math_CO", "math_DG", "math_FA", "math_GR", "math_LO",
         "math_NA", "math_NT", "math_OC", "math_PR", "math_RT", "math_ph"}
_CS = {"cs_CC", "cs_DS", "cs_IT", "cs_LG"}
TOPIC_CATS = {
    "linear algebra": _ALL, "probability": _ALL, "combinatorics": _ALL, "graph theory": _ALL,
    "logic and proofs": _ALL, "set theory": _ALL, "calculus": _ALL, "real analysis": _ALL,
    "statistics": {"stat_TH", "math_PR", "cs_LG", "cs_IT", "math_OC"},
    "abstract algebra": _MATH | {"cs_IT", "cs_CC"},
    "cryptography": {"cs_CC", "cs_IT", "math_NT"},
    "information theory": {"cs_IT", "cs_LG", "math_PR", "stat_TH"},
    "number theory": {"math_NT", "math_CO", "math_AG", "math_GR", "math_RT", "cs_CC", "cs_IT"},
    "learning theory": {"cs_LG", "stat_TH", "math_OC", "cs_IT"},
    "optimization": {"cs_LG", "math_OC", "math_NA", "cs_DS", "stat_TH"},
    "theory of computation": _CS | {"math_LO", "math_CO"},
    "algorithms": _CS | {"math_CO", "math_NA", "math_OC"},
    "geometry (euclidean/projective)": _MATH, "hyperbolic geometry": {"math_DG", "math_GR", "math_AT", "math_CA"},
    "numerical analysis": {"math_NA", "math_AP", "math_OC", "cs_LG", "math_ph"},
    "dynamical systems": {"math_AP", "math_CA", "math_ph", "math_PR", "math_NA", "math_OC", "math_DG"},
    "partial differential equations": {"math_AP", "math_NA", "math_ph", "math_PR", "math_DG", "math_FA", "math_CA", "math_OC"},
    "functional analysis": {"math_FA", "math_AP", "math_PR", "math_OC", "math_ph", "math_CA", "math_NA", "stat_TH", "cs_LG", "math_RT"},
    "distributions": {"math_AP", "math_FA", "math_ph", "math_CA", "math_PR"},
    "category theory": {"math_AG", "math_AT", "math_RT", "math_LO", "math_GR"},
    "stochastic processes": {"math_PR", "stat_TH", "math_AP", "math_ph", "cs_LG", "cs_IT", "math_OC", "math_NA"},
    "topology": _MATH, "complex analysis": {"math_CA", "math_AP", "math_NT", "math_AG", "math_FA", "math_ph", "math_DG", "math_PR"},
    "ordinary differential equations": {"math_CA", "math_AP", "math_NA", "math_ph", "math_OC", "math_DG", "math_PR"},
    "differential geometry": {"math_DG", "math_AP", "math_AT", "math_ph", "math_AG", "math_GR"},
    "measure theory": {"math_PR", "math_FA", "math_CA", "math_AP", "stat_TH", "math_ph", "math_OC", "cs_LG", "cs_IT"},
}


def _clean(text: str) -> str:
    """Prose words only: math, citations and references out, a macro's name out (its argument kept)."""
    t = re.sub(r"\$\$.*?\$\$|\$[^$]*\$|\\\[.*?\\\]|\\\(.*?\\\)", " ", text or "", flags=re.S)
    t = re.sub(r"\\begin\{(equation|align|eqnarray|multline|gather)\*?\}.*?\\end\{\1\*?\}", " ", t, flags=re.S)
    t = re.sub(r"\\(?:[a-z]*cite[a-z]*|ref|eqref|label|cref|Cref)\*?\s*(?:\[[^\]]*\])?\{[^{}]*\}", " ", t)
    t = re.sub(r"\\[A-Za-z]+\*?", " ", t)
    return re.sub(r"[{}~]", " ", t)


def _tokens(text: str) -> list[str]:
    return [norm_term(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]", _clean(text).lower())]


def _key(term: str) -> tuple:
    k = _tokens(term)
    while k and k[0] in _EDGE_WORDS:
        k = k[1:]
    while k and k[-1] in _EDGE_WORDS:
        k = k[:-1]
    return tuple(k)


def _defined_terms(raw: str) -> set:
    """Terms a definition emphasises (its definienda): \\emph{..}, \\textbf{..}, \\textit{..}."""
    return {_key(m) for m in re.findall(r"\\(?:emph|textbf|textit|textsl|em)\s*\{([^{}]{2,60})\}", raw or "")}


def load_index(concepts_path: Path) -> tuple[dict, dict]:
    """term key -> [concept id], and concept id -> {term, name, kind, books, words}."""
    g = json.loads(Path(concepts_path).read_text())
    cat = {b["id"]: b for b in json.loads((HERE / "foundation_books.json").read_text())["books"]}
    index, info = defaultdict(list), {}
    for c in g["concepts"]:
        # as the books write them (math still marked); a symbol for the concept is not a name for it
        terms = {m["term"] for m in c["members"] if not m.get("notation")}
        if c["kind"] == "result":
            terms = {t for t in terms | {m["name"] for m in c["members"] if m.get("name")} if RESULT_NAME.search(t)}
        keys = set()
        for t in terms:
            if re.search(r"\d", re.sub(r"\$[^$]*\$", "", t)):    # an instance ("cyclic group of order 12")
                continue
            k = _key(t)
            # a term is words: at least one word of 3+ letters, not a structural word
            if (k and len(k) <= _MAX_N and any(len(w) >= 3 for w in k) and " ".join(k) not in _GENERIC
                    and not _ROMAN & set(k)):
                keys.add(k)
        for k in keys:
            index[k].append(c["id"])
        cats = set()
        for b in c["books"]:
            # a reference source (ProofWiki) is not in the book catalogue: it serves every field
            for t in cat[b].get("topics", []) if b in cat else ["all fields"]:
                cats = cats | (_MATH | _CS | {"stat_TH"} if TOPIC_CATS.get(t, _ALL) == _ALL else TOPIC_CATS[t])
        info[c["id"]] = {"term": c["term"], "name": c["name"], "kind": c["kind"], "books": c["books"],
                         "cats": cats, "words": set().union(*(words(m["statement"]) for m in c["members"])),
                         "keys": keys,
                         # known only from reference subpages ("Prism/Height"): too narrow for a one-word term
                         "subpage_only": all("/" in (m.get("name") or "") for m in c["members"])}
    # a concept's cue words: its statements' words that few concepts use ("memory", "bits" for a
    # memory cell; not "set" or "let") and that are not its own term
    common = Counter(w for v in info.values() for w in v["words"])
    limit = 0.015 * len(info)
    for v in info.values():
        own = {w for k in v["keys"] for w in k}
        v["cues"] = {w for w in v["words"] if common[w] <= limit and w not in own}
    return dict(index), info


def match_node(text: str, index: dict) -> list[tuple]:
    """(term key, start token) of the terms in text, longest first, not overlapping."""
    toks = _tokens(text)
    out, i = [], 0
    while i < len(toks):
        for n in range(min(_MAX_N, len(toks) - i), 0, -1):
            k = tuple(toks[i:i + n])
            if k in index:
                out.append((k, i))
                i += n
                break
        else:
            i += 1
    return out


def _paper_hits(nodes: list, index: dict, category: str = "") -> tuple[list, set, set]:
    """(node id, term key, the term's candidate concepts, a definition of it) per occurrence, and
    the paper's words, and every term it uses. A one-word term keeps only the concepts of a field
    the category uses whose cue words the node shares (three of them)."""
    hits, paper_words, used = [], set(), set()
    for n in nodes:
        if n.get("type") in ("proof_step", "algorithm_step"):
            continue
        raw = n.get("raw_latex") or n.get("statement") or ""
        node_words = words(raw)
        paper_words |= node_words
        defined = _defined_terms(raw) if n.get("type") == "definition" else set()
        for k, _ in match_node(raw, index):
            used.add(k)
            cands = index[k]
            if len(k) == 1:
                cands = [c for c in cands if (not category or category in _INFO[c]["cats"])
                         and not _INFO[c]["subpage_only"] and len(_INFO[c]["cues"] & node_words) >= 3]
            if cands:
                hits.append((n["id"], k, cands, k in defined))
    return hits, paper_words, used


_INDEX = _INFO = None
_KNOWN_CATS = _MATH | _CS | {"stat_TH"}        # the categories TOPIC_CATS knows; any other is unrestricted


def _init(concepts_path):
    global _INDEX, _INFO
    _INDEX, _INFO = load_index(concepts_path)


def _papers_of(root: Path, unit: str):
    """The papers of one work unit: a category (category-folder or bundle layout) or a day archive
    (<root>/YYYY/MM/DD.tar.gz, the full-arXiv layout; the category comes from the id table)."""
    from corpus_io import iter_papers, read_papers
    if unit.endswith(".tar.gz"):
        yield from read_papers(Path(unit + "#*"), root)
    else:
        yield from iter_papers(root, categories=[unit])


def _scan_unit(args) -> tuple[list, Counter]:
    """One unit: per paper (id, category, grounding candidates (node, term, concept, confidence,
    defines), ambiguous count), and how many papers hold each term."""
    root, unit, min_margin = args
    papers, df = [], Counter()
    for p in _papers_of(Path(root), unit):
        cat = p.category if p.category in _KNOWN_CATS else ""
        hits, pw, used = _paper_hits(p.nodes, _INDEX, cat)
        df.update(used)                       # every use counts: "sum" is common in any sense
        found, ambiguous = [], 0
        for nid, k, cands, defines in hits:
            cid, conf = _choose(cands, pw, min_margin)
            if cid is None:
                ambiguous += 1
            else:
                found.append((nid, k, cid, conf, defines))
        papers.append((p.paper_id, p.category or "unknown", found, ambiguous))
    return papers, df


def _choose(cands: list, paper_words: set, min_margin: float):
    """The concept a term means in this paper, or None when its homonyms are not told apart: the one
    whose book statements share most words with the paper, by a margin."""
    if len(cands) == 1:
        return cands[0], 1.0
    score = sorted(((len(_INFO[c]["words"] & paper_words) / (len(_INFO[c]["words"]) ** 0.5 or 1), c)
                    for c in cands), reverse=True)
    (s1, c1), (s2, _) = score[0], score[1]
    if s1 <= 0 or s1 - s2 < min_margin * s1:
        return None, 0.0
    return c1, round(1 - s2 / s1, 2)


def work_units(root: Path, categories=None, years=None) -> list[str]:
    """Categories (category layout) or day archives (full-arXiv layout, optionally some years)."""
    from corpus_io import walk, _category_from_path
    archives = []
    cats = set()
    for p in walk(root):
        if p.name.endswith("#*"):
            archives.append(str(p)[:-2])
        else:
            cats.add(_category_from_path(p, root))
    if archives:
        if years:
            years = {str(y) for y in years}
            archives = [a for a in archives if Path(a).relative_to(root).parts[0] in years]
        return archives
    return sorted(categories or cats)


def scan(root: Path, units: list, jobs: int, min_margin: float, concepts_path: Path) -> tuple[list, Counter]:
    """All units, in parallel: the per-paper candidates and the pooled term document frequencies."""
    papers, df = [], Counter()
    with Pool(jobs, initializer=_init, initargs=(concepts_path,)) as pool:
        for ps, d in pool.imap_unordered(_scan_unit, [(str(root), u, min_margin) for u in units]):
            papers.extend(ps)
            df.update(d)
    return papers, df


def finalize(scans, df: Counter, n_papers: int, out: Path, max_df: float, min_margin: float,
             concepts_path: Path) -> dict:
    """Generic terms from the pooled frequencies, then one <category>.jsonl of grounding edges and
    summary.json. `scans` yields lists of scanned papers (one list per scan file), streamed, so the
    whole arXiv is never in memory at once."""
    _init(concepts_path)
    generic = {k for k, v in df.items() if v > max_df * n_papers}
    out.mkdir(parents=True, exist_ok=True)
    stats, used, cats = Counter(), Counter(), set()
    files = {}
    try:
        for papers in scans:
            for pid, cat, found, ambiguous in sorted(papers, key=lambda p: (p[1], p[0])):
                if cat not in files:
                    files[cat] = open(out / f"{cat}.jsonl", "w", encoding="utf-8")
                    cats.add(cat)
                stats["ambiguous"] += ambiguous
                edges, seen = [], set()
                for nid, k, cid, conf, defines in found:
                    if k in generic:
                        stats["generic"] += 1
                        continue
                    if (nid, cid) in seen:
                        continue
                    seen.add((nid, cid))
                    idf = math.log(n_papers / df[k])
                    edges.append({"source": nid, "target": cid, "type": "grounded_to",
                                  "term": " ".join(k), "basis": "defines" if defines else "term",
                                  "confidence": round(min(1.0, conf * min(1.0, idf / 5)), 2)})
                    used[cid] += 1
                stats["edges"] += len(edges)
                stats["papers_grounded"] += bool(edges)
                files[cat].write(json.dumps({"paper_id": pid, "edges": edges}, ensure_ascii=False) + "\n")
    finally:
        for fh in files.values():
            fh.close()
    summary = {"concepts": str(concepts_path), "papers": n_papers, "categories": sorted(cats),
               "max_df": max_df, "min_margin": min_margin, "generic_terms": len(generic),
               **stats, "concepts_used": len(used),
               "top_generic": [" ".join(k) for k, _ in sorted(((k, df[k]) for k in generic), key=lambda x: -x[1])[:60]],
               "top_concepts": [(_INFO[c]["name"], n) for c, n in used.most_common(40)]}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def ground(root: Path, out: Path, categories=None, jobs: int = 8, max_df: float = 0.10,
           min_margin: float = 0.25, concepts_path: Path = ROOT / "concepts.json", years=None) -> dict:
    """Scan and finalize in one go (the 100K: ~12 min on 8 cores)."""
    root, out = Path(root), Path(out)
    units = work_units(root, categories, years)
    papers, df = scan(root, units, jobs, min_margin, concepts_path)
    return finalize([papers], df, len(papers), out, max_df, min_margin, concepts_path)


def _scan_paths(out: Path, name: str) -> tuple[Path, Path]:
    """A scan's two files: its term frequencies (small) and its papers (large, read once at the end)."""
    return out / "scan" / f"{name}.df.pkl.gz", out / "scan" / f"{name}.papers.pkl.gz"


def _load(p: Path):
    with gzip.open(p, "rb") as fh:
        return pickle.load(fh)


def _dump(obj, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root", nargs="?", help="paper graphs (corpus_io layout, bundles, or the full-arXiv day archives)")
    ap.add_argument("--out", default=str(ROOT / "grounding"))
    ap.add_argument("--categories", nargs="*")
    ap.add_argument("--years", nargs="*", help="day-archive layout: only these years (one SLURM task per year)")
    ap.add_argument("--cats", default=None, help="id -> category table (.tsv[.gz]) for the day-archive layout")
    ap.add_argument("--scan-only", default=None, metavar="NAME",
                    help="write the scan to <out>/scan/NAME.pkl.gz and stop (pool the scans with --finalize)")
    ap.add_argument("--finalize", action="store_true", help="pool every <out>/scan/*.pkl.gz and write the edges")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--max-df", type=float, default=0.10, help="a term in more of the papers is common vocabulary")
    ap.add_argument("--min-margin", type=float, default=0.25, help="how much closer the chosen homonym must be")
    ap.add_argument("--concepts", default=str(ROOT / "concepts.json"))
    a = ap.parse_args()
    out, concepts = Path(a.out), Path(a.concepts)
    if a.cats:
        from corpus_io import set_categories
        print(f"[ground] {set_categories(a.cats)} ids in the category table", file=sys.stderr)
    if a.finalize:
        names = sorted(p.name[:-len(".df.pkl.gz")] for p in (out / "scan").glob("*.df.pkl.gz"))
        df, n_papers = Counter(), 0
        for name in names:
            d, n = _load(_scan_paths(out, name)[0])
            df.update(d)
            n_papers += n
            print(f"[ground] {name}: {n} papers", file=sys.stderr)
        scans = (_load(_scan_paths(out, name)[1]) for name in names)
        s = finalize(scans, df, n_papers, out, a.max_df, a.min_margin, concepts)
    elif a.scan_only:
        units = work_units(Path(a.root), a.categories, a.years)
        papers, df = scan(Path(a.root), units, a.jobs, a.min_margin, concepts)
        pdf, pp = _scan_paths(out, a.scan_only)
        _dump((df, len(papers)), pdf)
        _dump(papers, pp)
        s = {"scan": str(pp), "units": len(units), "papers": len(papers), "terms": len(df)}
    else:
        s = ground(Path(a.root), out, a.categories, a.jobs, a.max_df, a.min_margin, concepts, a.years)
    print(json.dumps({k: v for k, v in s.items() if not k.startswith("top_")}))


if __name__ == "__main__":
    main()
