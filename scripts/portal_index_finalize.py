"""Portal listing for the all_v7g categories: python3 scripts/portal_index_finalize.py; then: hf upload saranga-project/saranga site all_v7g/_portal_index --repo-type dataset
Joins the per-bundle-category rows (parts/<CAT>.jsonl, portal_index_cat.py) with the arXiv titles of the
Kaggle snapshot, folds the pre-1998 archives into their modern categories and stat.TH's math_ST bundles,
and writes site/index.json (categories with field, counts per year) + site/<category>/<year>.json (rows)."""
import gzip, json, re, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "/sci/labs/orzuk/yaron.otmazgin/Authomathics/portal")
import bundle_t3 as B
D = Path("/sci/labs/orzuk/yaron.otmazgin/portal_index")
SNAP = "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/arxiv-metadata-oai-snapshot.json"
LEGACY = {"alg-geom": "math.AG", "dg-ga": "math.DG", "funct-an": "math.FA", "q-alg": "math.QA", "math_ST": "stat.TH"}
FIELD = [("math", "Mathematics"), ("cs", "Computer Science"), ("stat", "Statistics"), ("econ", "Economics"),
         ("eess", "Electrical Engineering and Systems Science"), ("q-fin", "Quantitative Finance"), ("nlin", "Physics")]
def display(c): return LEGACY.get(c) or c.replace("_", ".", 1)
def field(c): return "Physics" if c == "math-ph" else next(f for p, f in FIELD if c.startswith(p))  # math-ph is a physics archive on arXiv
rows = []
for p in sorted((D / "parts").glob("*.jsonl")):
    bc = p.stem
    for line in open(p):
        r = json.loads(line); r["bc"] = bc; rows.append(r)
want = {B.paper_key(r["stem"]) for r in rows}
title = {}
with open(SNAP) as fh:
    for line in fh:
        i = line.index('"id":"') + 6; k = line[i:line.index('"', i)]
        if k in want: title[k] = " ".join(json.loads(line)["title"].split())
print(f"{len(rows)} rows, {len(title)} titles", flush=True)
out = defaultdict(list)
for r in rows:
    c, s = display(r["bc"]), r["stem"]
    out[(c, r["year"])].append({"paper_id": s.removesuffix("_rules"), "title": title.get(B.paper_key(s), ""),
        "n_nodes": r["n_nodes"], "n_edges": r["n_edges"], "buckets": r["buckets"], "acyclic": r["acyclic"],
        "tier": 3, "category": c, "json_path": f"t3json?cat={r['bc']}&id={s}", "graph_path": f"render3?cat={r['bc']}&id={s}"})
site = D / "site"; cats = defaultdict(lambda: {"count": 0, "nodes": 0, "years": {}})
for (c, y), rs in sorted(out.items()):
    rs.sort(key=lambda x: x["paper_id"])
    (site / c).mkdir(parents=True, exist_ok=True)
    (site / c / f"{y}.json").write_text(json.dumps(rs, ensure_ascii=False, separators=(",", ":")))
    k = cats[c]; k["count"] += len(rs); k["nodes"] += sum(x["n_nodes"] for x in rs); k["years"][y] = len(rs)
idx = {"source": "all_v7g (whole-arXiv v7 run with the textbook grounding); categories with mean DAG depth >= 5 and >= 500 papers",
       "categories": [{"category": c, "field": field(c), "count": k["count"], "avg_nodes": round(k["nodes"] / k["count"], 1),
                       "years": k["years"]} for c, k in sorted(cats.items())]}
with gzip.open(site / "_ids.tsv.gz", "wt", encoding="utf-8") as fh:     # for "Your paper": id -> its page
    for r in rows: fh.write(f"{B.paper_key(r['stem']).replace('/', '_')}\t{r['bc']}\t{r['stem']}\n")
(site / "index.json").write_text(json.dumps(idx, indent=1))
print(len(cats), "categories,", sum(k["count"] for k in cats.values()), "papers,", len(out), "category-year files")
