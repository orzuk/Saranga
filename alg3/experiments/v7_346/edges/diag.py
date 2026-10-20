"""Which signals cover the silver edges we miss, per kind (TRAIN+VAL only)."""
import collections, csv, json, math, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO / "src/LLMVersion"), str(REPO / "src"), str(REPO / "alg3")]
import edge_metrics as EM, edges as ED
from graph_io import load_graph
import latex_facts as L
C = REPO / "alg3/cache/v7_346"; G = REPO / "alg3/runs/v7_346/graphs"
split = {r["arxiv_id"]: r["split"] for r in csv.DictReader(open(C / "split_A.csv"))}
pids = sorted(p for p, s in split.items() if s == sys.argv[1])
sq = lambda t: re.sub(r"\s+", "", t or "")
REF = re.compile(r"\\(?:eq|c|C|auto)?ref\*?\{([^{}]+)\}"); LAB = re.compile(r"\\label\{([^{}]+)\}")
WORD = re.compile(r"[A-Za-z]{4,}|\\[A-Za-z]+")
cov = collections.defaultdict(collections.Counter); cand = collections.Counter()
for pid in pids:
    tex = sq(open(L.find_main_tex(C / "tex" / pid / "source"), errors="ignore").read())
    pn, pe = load_graph(G / "T-A" / f"{pid}.json")
    rn, re_ = EM.level1(*load_graph(C / "silver" / f"{pid}.json"))
    rid = {n["id"]: n for n in rn}
    al = EM.align(pn, rn); inv = {v: k for k, v in al.items()}
    by = {n["id"]: n for n in pn}
    pos = {}
    for n in pn:
        t = sq(ED.node_text(n)); k = tex.find(t[len(t)//3: len(t)//3 + 50]) if len(t) > 60 else tex.find(t)
        pos[n["id"]] = k
    rank = {i: r for r, i in enumerate(sorted(pos, key=lambda i: pos[i]))}
    labs = {n["id"]: set(LAB.findall(ED.node_text(n))) for n in pn}
    refs = {n["id"]: set(REF.findall(ED.node_text(n))) for n in pn}
    toks = {n["id"]: set(WORD.findall(ED.node_text(n))) for n in pn}
    df = collections.Counter(t for s in toks.values() for t in s)
    N = len(pn)
    def rare(a, b):
        sh = toks[a] & toks[b]
        return sum(math.log(N / df[t]) for t in sh if df[t] <= max(2, N * 0.05))
    pedges = {(e["source"], e["target"]) for e in pe}
    # term channel candidates (existing pair generator)
    import pickle
    term = set()
    dm = ED.EdgeModel(REPO / "extractors/edges/silver_v7__edges_stack__2026-10").dmodel
    for d, x, _f in ED.pairs_of(pn, dm): term.add((d, x))
    gold = set()
    for e in re_:
        s, t = inv.get(e["source"]), inv.get(e["target"])
        if s and t and s != t: gold.add((s, t, EM.edge_kind(e, rid)))
    gpairs = {(s, t) for s, t, _ in gold}
    def channels(s, t):
        ch = []
        if (s, t) in term: ch.append("term")
        if labs[s] & refs[t]: ch.append("ref")
        if (s, t) in pedges or (t, s) in pedges: ch.append("parser")
        if pos[s] >= 0 and pos[t] >= 0 and abs(rank[s] - rank[t]) <= 2: ch.append("adj2")
        if pos[s] >= 0 and pos[t] >= 0 and pos[s] < pos[t] and rank[t] - rank[s] <= 6: ch.append("prev6")
        if rare(s, t) >= 3: ch.append("rare")
        return ch
    for s, t, k in gold:
        ch = channels(s, t); c = cov[k]; c["n"] += 1
        for x in ch: c[x] += 1
        c["any"] += bool(ch); c["any_but_term"] += bool([x for x in ch if x != "term"])
        c["s_before_t"] += pos[s] < pos[t]
    # channel volume: all ordered pairs among aligned+unaligned pred nodes (non-gold) per channel
    ids = list(by)
    for s in ids:
        for t in ids:
            if s == t: continue
            for x in channels(s, t):
                cand[x, (s, t) in gpairs] += 1
print("kind               n   " + "  ".join(f"{x:>6}" for x in ("term","ref","parser","adj2","prev6","rare","any","s<t")))
for k, c in sorted(cov.items(), key=lambda kv: -kv[1]["n"]):
    print(f"{k:16} {c['n']:5}  " + "  ".join(f"{c[x]/c['n']:6.2f}" for x in ("term","ref","parser","adj2","prev6","rare","any","s_before_t")))
print("\nchannel volume (pairs proposed): positives / total = precision")
for x in ("term","ref","parser","adj2","prev6","rare"):
    tp, fp = cand[x, True], cand[x, False]; print(f"  {x:7} {tp:7} / {tp+fp:8} = {tp/max(1,tp+fp):.3f}")
