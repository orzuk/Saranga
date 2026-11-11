"""Portal listing rows for one bundle category of all_v7g:  python3 scripts/portal_index_cat.py CAT  (SLURM array over the 61 bundle folders of the 57 categories)
Reads every <CAT>/<year>.json.xz bundle and writes OUT/parts/<CAT>.jsonl, one row per paper:
the bundle year, id, node/edge counts (paper's own graph, grounding edges excluded), type buckets, acyclic flag."""
import json, sys
from pathlib import Path
import networkx as nx
sys.path.insert(0, "/sci/labs/orzuk/yaron.otmazgin/Authomathics/portal")
import bundle_t3 as B
CAT = sys.argv[1]
SRC = Path("/sci/labs/orzuk/yaron.otmazgin/bundles/all_v7g") / CAT
OUT = Path("/sci/labs/orzuk/yaron.otmazgin/portal_index/parts"); OUT.mkdir(parents=True, exist_ok=True)
BUCKETS = {"def": {"definition"}, "thm": {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"},
           "alg": {"algorithm"}, "pf": {"proof"}, "steps": {"proof_step", "algorithm_step"},
           "other": {"equation", "problem", "open_problem", "assumption", "example", "remark"}}
n = 0
with open(OUT / f"{CAT}.jsonl.tmp", "w") as out:
    for ixf in sorted(SRC.glob("*.idx.json")):
        year = ixf.name.split(".")[0]
        ix = json.loads(ixf.read_text())
        with open(SRC / f"{year}.json.xz", "rb") as fh:
            for stem, e in ix.items():
                fh.seek(e[0]); d = B.unpack(fh.read(e[1]), e)
                nodes = [x for x in d.get("nodes", []) if x.get("origin", "paper") == "paper"]
                ids = {x["id"] for x in nodes}
                es = [(x["source"], x["target"]) for x in d.get("edges", [])
                      if x.get("type") != "grounded_to" and x["source"] in ids and x["target"] in ids]
                g = nx.DiGraph(es)
                tc = {}
                for x in nodes: tc[x.get("type")] = tc.get(x.get("type"), 0) + 1
                out.write(json.dumps({"year": year, "stem": stem, "n_nodes": len(nodes), "n_edges": len(es),
                    "buckets": {b: sum(tc.get(t, 0) for t in ts) for b, ts in BUCKETS.items()},
                    "acyclic": nx.is_directed_acyclic_graph(g)}) + "\n")
                n += 1
(OUT / f"{CAT}.jsonl.tmp").rename(OUT / f"{CAT}.jsonl")
print(CAT, n, "papers")
