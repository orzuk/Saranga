"""Corpus nodes that mention the Kourovka Notebook, with the problem number when given."""
import glob, json, re
C = "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v7"
NUM = re.compile(r"(?:problem|question|conjecture)s?\s*~?\s*(\d{1,2}\.\d{1,3})|(\d{1,2}\.\d{1,3})\s*(?:\]|\}|\)|of|in)", re.I)
out, papers = [], set()
for f in glob.glob(f"{C}/*/json/*.json"):
    s = open(f, errors="ignore").read()
    if "ourovka" not in s:
        continue
    d = json.loads(s)
    a = d["metadata"]["paper_id"]
    papers.add(a)
    for n in d["nodes"]:
        t = n.get("raw_latex") or n.get("statement") or ""
        if "ourovka" in t:
            nums = sorted({x for m in NUM.finditer(t) for x in m.groups() if x})
            out.append({"paper": a, "node": n["id"], "type": n.get("type"), "nums": nums, "text": t[:800]})
json.dump(out, open("kourovka_nodes.json", "w"))
print(len(papers), "papers mention Kourovka;", len(out), "nodes;", sum(1 for o in out if o["nums"]), "with a number")
