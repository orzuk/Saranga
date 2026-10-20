import sys, csv, collections
from pathlib import Path
sys.path[:0]=["src/LLMVersion","src"]
import edge_metrics as EM
from graph_io import load_graph
C=Path("alg3/cache/v7_346"); split={r["arxiv_id"]:r["split"] for r in csv.DictReader(open(C/"split_A.csv"))}
for d in sys.argv[1:]:
    tot=collections.Counter(); found=collections.Counter(); P=TP=0
    for p,s in split.items():
        if s!="val": continue
        rn,re_=EM.level1(*load_graph(C/"silver"/f"{p}.json")); rid={n["id"]:n for n in rn}
        pn,pe=load_graph(f"{d}/{p}.json"); al=EM.align(pn,rn)
        pred={(al.get(e["source"]),al.get(e["target"])) for e in pe if al.get(e["source"])!=al.get(e["target"]) or al.get(e["source"]) is None}
        P+=len([e for e in pe if not (al.get(e["source"]) is not None and al.get(e["source"])==al.get(e["target"]))])
        for e in re_:
            if e["source"] in rid and e["target"] in rid:
                b=e.get("basis","?"); tot[b]+=1; f=(e["source"],e["target"]) in pred; found[b]+=f; TP+=f
    R=TP/sum(tot.values()); Pr=TP/P
    print(f"{Path(d).name:12} P {Pr:.3f} R {R:.3f} F1 {2*Pr*R/(Pr+R):.3f} | " + "  ".join(f"{b} {found[b]/tot[b]:.2f}" for b in ("term","ref","syntax","named","inferred")))
