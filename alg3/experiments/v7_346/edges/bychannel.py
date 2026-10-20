import sys, csv, collections, json
from pathlib import Path
sys.path[:0]=["alg3","src/LLMVersion","src"]
import edges_all as EA, edge_metrics as EM
from graph_io import load_graph
C=Path("alg3/cache/v7_346"); split={r["arxiv_id"]:r["split"] for r in csv.DictReader(open(C/"split_A.csv"))}
m=EA.Model(sys.argv[1]); th=float(sys.argv[2]) if len(sys.argv)>2 else m.threshold
st=collections.Counter()
for p,s in split.items():
    if s!="val": continue
    g=json.load(open(f"alg3/runs/v7_346/graphs/T-A/{p}.json"))
    v,scored=EA.score_graph(g, EA._tex_of(C/"tex",p), m)
    feats={(a,b):f for a,b,f in EA.candidates(v, m.dmodel)}
    rn,re_=EM.level1(*load_graph(C/"silver"/f"{p}.json")); rid={n["id"]:n for n in rn}
    al=EM.align(v.nodes,rn)
    gold={(e["source"],e["target"]):e.get("basis") for e in re_ if e["source"] in rid and e["target"] in rid}
    for a,b,q in scored:
        f=feats[(a,b)]
        main=("term" if "ch:term" in f else "ref" if "ch:ref" in f else "parser" if "ch:parser" in f else "other")
        lab=gold.get((al.get(a),al.get(b)))
        st[main,"cand"]+=1; st[main,"cand_pos"]+=lab is not None
        if q>=th: st[main,"pred"]+=1; st[main,"tp"]+=lab is not None
print(f"threshold {th}")
for k in ("term","ref","parser","other"):
    print(f"{k:7} candidates {st[k,'cand']:7} (pos {st[k,'cand_pos']:5}) | predicted {st[k,'pred']:6}  precision {st[k,'tp']/max(1,st[k,'pred']):.3f}  tp {st[k,'tp']}")
