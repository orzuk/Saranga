"""Summarise the grounding layer of 1603.04246 (LLM and rules graphs) for SUMMARY.md."""
import json, shutil
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).parent
D = Path("/mnt/c/Code/Github/Saranga/corpus/case_studies/viazovska_2016")
C = json.load(open("/mnt/c/Datasets/Saranga_data/foundation/books_v7b/concepts.json"))
cinfo = {c["id"]: c for c in C["concepts"]}
LLM = json.load(open("/mnt/c/Code/Github/Saranga/corpus/silver/opus-5.5__v7_cases/viazovska_2016.json"))
RUL = json.load(open(D / "viazovska_2016_rules.json"))
out = {}
(D / "grounding").mkdir(exist_ok=True)
for name, g in (("llm", LLM), ("rules", RUL)):
    rows = [json.loads(l) for l in open(HERE / f"gout_{name}/math_NT.jsonl")]
    row = next(r for r in rows if r["paper_id"] == "1603.04246")
    json.dump(row, open(D / f"grounding/grounding_{name}.json", "w"), indent=1, ensure_ascii=False)
    shutil.copy(HERE / f"gout_{name}/summary.json", D / f"grounding/summary_{name}.json")
    by = {n["id"]: n for n in g["nodes"]}
    per = defaultdict(set)
    terms = {}
    for e in row["edges"]:
        per[e["target"]].add(e["source"])
        terms[e["target"]] = e["term"]
    def src(c):
        b = cinfo[c]["books"]
        b = b if isinstance(b, list) else eval(b)
        return b
    conc = sorted(per, key=lambda c: -len(per[c]))
    out[name] = {"edges": len(row["edges"]), "concepts": len(per),
                 "nodes_grounded": len({e["source"] for e in row["edges"]}),
                 "defines": sum(e["basis"] == "defines" for e in row["edges"]),
                 "kinds": Counter(cinfo[c]["kind"] for c in per),
                 "proofwiki_only": sum(all("proofwiki" in b.lower() or "naturalproofs" in b.lower() for b in src(c)) for c in per),
                 "top": [(cinfo[c]["name"], terms[c], cinfo[c]["kind"], len(per[c]), len(src(c))) for c in conc[:40]],
                 "all": sorted(cinfo[c]["name"] for c in per)}
    if name == "llm":
        # which concepts the main chain rests on: grounded nodes that support Theorem 1
        out["llm"]["by_section"] = Counter(by[e["source"]].get("section") for e in row["edges"])
        out["llm"]["external_nodes_grounded"] = sum(by[s]["origin"] == "external" for s in {e["source"] for e in row["edges"]})
L, R = set(out["llm"]["all"]), set(out["rules"]["all"])
out["overlap"] = {"common": len(L & R), "llm_only": sorted(L - R), "rules_only": sorted(R - L)}
json.dump(out, open(D / "grounding/grounding_analysis.json", "w"), indent=1, ensure_ascii=False, default=list)
print(json.dumps(out, indent=1, ensure_ascii=False, default=list)[:12000])
