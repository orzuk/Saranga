"""ID-free Benchmark-1 scoring on the 10 T1 gold papers.
Text: statement with $...$, \\[..\\], \\(..\\) and display envs replaced by [MATH] (the gold's own convention),
tokens as in src/evaluate_extraction (Jaccard, threshold 0.5), same type required, greedy one-to-one.
Proofs: matched when the results they prove are matched to each other (else by text).
External-origin nodes excluded on both sides. Reports corpus macro-F1 over the 9 target types."""
import json, random, re, sys
from pathlib import Path
REPO = Path("/mnt/c/Code/Github/Saranga"); sys.path[:0] = [str(REPO/"src")]
import evaluate_extraction as E
T1 = REPO/"portal/data/tier1"
TYPES = ["theorem","lemma","proposition","corollary","claim","conjecture","problem","definition","proof"]
MATH = re.compile(r"\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\)|\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}", re.S)
def norm(t): return MATH.sub(" [MATH] ", t or "")
def load(p):
    d = json.load(open(p)); ns = d.get("nodes", d.get("objects", []))
    return [n for n in ns if n.get("origin","paper") != "external" and n.get("type") in TYPES]
def text(n): return norm(n.get("statement") or n.get("raw_latex") or "")
def match(ext, gold, thr=0.5):
    cand = []
    for i,a in enumerate(ext):
        if a["type"]=="proof": continue
        for j,b in enumerate(gold):
            if b["type"]!=a["type"]: continue
            s = E.jaccard(text(a), text(b))
            if s>=thr: cand.append((s,i,j))
    cand.sort(reverse=True); ue, ug, m = set(), set(), {}
    for s,i,j in cand:
        if i in ue or j in ug: continue
        ue.add(i); ug.add(j); m[i]=j
    eid = {a.get("id"):i for i,a in enumerate(ext)}; gid = {b.get("id"):j for j,b in enumerate(gold)}
    for i,a in enumerate(ext):          # proofs: via the matched result
        if a["type"]!="proof": continue
        ti = eid.get(a.get("proves"))
        if ti is None or ti not in m: continue
        tj = m[ti]
        for j,b in enumerate(gold):
            if b["type"]=="proof" and j not in ug and gid.get(b.get("proves"))==tj:
                ue.add(i); ug.add(j); m[i]=j; break
    c = {t:[0,0,0] for t in TYPES}
    for i,a in enumerate(ext):
        c[a["type"]][0 if i in m else 1] += 1
    for j,b in enumerate(gold):
        if j not in ug: c[b["type"]][2] += 1
    return c
def f1(tp,fp,fn): d=2*tp+fp+fn; return 2*tp/d if d else 0
def macro(L):
    s={t:[0,0,0] for t in TYPES}
    for c in L:
        for t in TYPES:
            for k in range(3): s[t][k]+=c[t][k]
    v=[f1(*s[t]) for t in TYPES if s[t][0]+s[t][2]>0]
    return sum(v)/len(v), s
def run(d, suffix, label, show=False):
    L=[]
    for g in sorted(T1.glob("*_manual.json")):
        aid=g.stem.replace("_manual",""); e=Path(d)/f"{aid}{suffix}.json"
        if e.exists(): L.append(match(load(e), load(g)))
    m,s=macro(L); rng=random.Random(42); bs=sorted(macro([rng.choice(L) for _ in L])[0] for _ in range(3000))
    print(f"{label:30s} n={len(L)} macro-F1 {m:.3f} [{bs[75]:.3f}, {bs[2925]:.3f}]")
    if show:
        for t in TYPES: print(f"     {t:12s} gold {s[t][0]+s[t][2]:3d} TP {s[t][0]:3d} FP {s[t][1]:3d} F1 {f1(*s[t]):.2f}")
if __name__=="__main__":
    run("portal/data/tier1","_anthropic","Opus 4.6 (old)")
    run("portal/data/tier1","_openai","GPT-4o (old)")
    run("portal/data/tier1","_rules","old manual rules")
    run("corpus/gold/opus-5.5__v6","","Opus 5.5 v6 (current)",True)
    run("corpus/gold/base_parser","","base parser")
    run("corpus/gold/rules_v6","","parser + sentence rules",True)
