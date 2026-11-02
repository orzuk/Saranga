"""Atlas pilot: problems and the results that resolve them, over the SARANGA v7 100K corpus, with citations
resolved to arXiv papers (and, where possible, the cited statement) through TheoremGraph's citation table.

Links collected per paper of the corpus:
  restated  a conjecture / open_problem / problem node whose LaTeX cites its source (\\cite[Conjecture 7]{key})
  claim     a theorem-like node whose statement says it settles a cited problem ("we prove the conjecture of
            \\cite{key}", "answers a question of", "a counterexample to", ...)
  edge      a resolves edge of the extraction (problem -> result), with the problem's citations if any
"""
import csv, json, os, re, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/discovery/common"))
from corpus_io import walk, read_json      # per-paper JSONs or bundles
csv.field_size_limit(10**9)
TG = "/sci/labs/orzuk/orzuk/projects/Authomathics/theoremgraph"
CORPUS = sys.argv[1] if len(sys.argv) > 1 else \
    "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v7"
PROB = {"conjecture", "open_problem", "problem"}
RESULT = {"theorem", "lemma", "proposition", "corollary", "claim"}
CITE = re.compile(r"\\cite[a-zA-Z]*\*?\s*(?:\[([^\]]*)\])?\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}")
PWORD = re.compile(r"conjectur|question|problem|hypothes", re.I)
VERB = re.compile(r"\b(prove|proves|proved|proving|confirm|answer|resolv|settl|disprov|refut|solv|affirmativ|negativ|"
                  r"counterexample|counter-example|holds|is true|is false|establish|verif)", re.I)
strip_v = lambda a: re.sub(r"v\d+$", "", a)

def cites(tex):
    out = []
    for m in CITE.finditer(tex or ""):
        opt = (m.group(2) or m.group(1) or "").strip()
        for k in m.group(3).split(","):
            if k.strip():
                out.append((k.strip(), opt))
    return out

# 1. the corpus papers and what they cite
papers = {}                                   # arxiv id (no version) -> category
for f in walk(Path(CORPUS)):
    a = f.name.split("#")[-1].replace("_rules.json", "").replace("_rules", "").replace(".json", "")
    papers[strip_v(a)] = (f, a)
print(len(papers), "corpus papers", flush=True)
links, stats = [], collections.Counter()
for a0, (f, a) in papers.items():
    try:
        d = read_json(f)
    except Exception:
        stats["unreadable"] += 1
        continue
    nodes = {n["id"]: n for n in d["nodes"]}
    for n in d["nodes"]:
        t, tex = n.get("type"), n.get("raw_latex") or n.get("statement") or ""
        if t in PROB:
            stats["problems"] += 1
            c = cites(tex)
            if c:
                stats["problems_citing"] += 1
                links.append({"kind": "restated", "paper": a0, "node": n["id"], "type": t, "cites": c, "text": tex[:600]})
        elif t in RESULT and "cite" in tex and PWORD.search(tex) and VERB.search(tex):
            c = cites(tex)
            if c:
                stats["claims"] += 1
                links.append({"kind": "claim", "paper": a0, "node": n["id"], "type": t, "cites": c, "text": tex[:600]})
    for e in d["edges"]:
        if e.get("type") == "resolves":
            stats["resolves_edges"] += 1
            s, g = nodes.get(e["source"], {}), nodes.get(e["target"], {})
            c = cites(s.get("raw_latex") or "")
            links.append({"kind": "edge", "paper": a0, "node": e["target"], "problem": e["source"], "cites": c,
                          "text": (s.get("raw_latex") or "")[:300] + " ==> " + (g.get("raw_latex") or "")[:300]})
print(dict(stats), flush=True)

# 2. TheoremGraph: arXiv ids of its papers, and each corpus paper's cite keys -> cited paper
tg_id, tg_arxiv = {}, {}
with open(f"{TG}/paper_arxiv.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        a = strip_v((r.get("arxiv_id") or "").strip())
        tg_arxiv[r["paper_id"]] = a
        if a in papers:
            tg_id[a] = r["paper_id"]
print(len(tg_id), "corpus papers in TheoremGraph", flush=True)
want = set(tg_id.values())
st_paper = {}
with open(f"{TG}/statement_informal.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        st_paper[r["statement_id"]] = (r["paper_id"], (r["kind"] or "").lower(), (r["ref"] or "").strip())
keymap = {}                                    # (TG paper, cite key) -> cited TG paper
with open(f"{TG}/informal_dependency.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        if r["cite_id"] and r["cite_key"]:
            p = st_paper.get(r["src_id"], (None,))[0]
            if p in want:
                keymap[(p, r["cite_key"])] = r["cite_id"]
print(len(keymap), "cite keys resolved for corpus papers", flush=True)
by_ref = collections.defaultdict(dict)        # cited TG paper -> {(kind, ref): statement}
for sid, (p, k, ref) in st_paper.items():
    if k in ("conjecture", "hypothesis", "question", "problem") and ref:
        by_ref[p][ref] = sid

# 3. resolve
NUM = re.compile(r"(conjecture|question|problem|hypothesis|conj\.)\s*~?\s*([0-9][0-9.]*[0-9a-z]?)", re.I)
res = collections.Counter()
for l in links:
    p = tg_id.get(l["paper"])
    l["cited"] = []
    for key, opt in l["cites"]:
        cid = keymap.get((p, key)) if p else None
        ent = {"key": key, "opt": opt, "arxiv": tg_arxiv.get(cid) if cid else None}
        m = NUM.search(opt or "") or (NUM.search(l["text"]) if len(l["cites"]) == 1 else None)
        if cid and m:
            ent["statement"] = by_ref.get(cid, {}).get(m.group(2).rstrip("."))
        l["cited"].append(ent)
    res[(l["kind"], "any_cite_to_arxiv")] += any(c["arxiv"] for c in l["cited"])
    res[(l["kind"], "to_statement")] += any(c.get("statement") for c in l["cited"])
    res[(l["kind"], "total")] += 1
    res[(l["kind"], "paper_in_tg")] += bool(p)
print({f"{k}:{v}": n for (k, v), n in sorted(res.items())}, flush=True)
json.dump({"stats": dict(stats), "resolution": {f"{k}:{v}": n for (k, v), n in res.items()}, "links": links},
          open("atlas_pilot.json", "w"))
