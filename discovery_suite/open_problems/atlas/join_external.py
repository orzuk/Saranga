"""Candidate matches between kept atlas problems and external status lists (VibeMathed, OpenAI math families,
Erdős problems, Kourovka). Exact joins by Erdős / Kourovka number; TF-IDF top-3 for the rest."""
import json, re, sys, collections
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
S = sys.argv[1]
L = json.load(open(f"{S}/atlas/links_rc.json")); V = json.load(open(f"{S}/atlas/verdicts.json"))
keep = [(int(i), f) for i, f in V.items() if f[1] == "y"]
def doc(i, f): return f"{f[4]} {f[5]} " + re.sub(r"\\[a-zA-Z]+|[{}$]", " ", L[i]["text"])[:400]
A = [doc(i, f) for i, f in keep]
ext = []
vm = json.load(open(f"{S}/dl_vm/dataset.json"))["problems"]
for e in vm:
    ext.append({"src": "vibemathed", "id": e["slug"], "name": e.get("shortName") or e["name"], "resolution": e.get("resolution"),
                "num": e.get("problemNumber"), "text": f'{e["name"]} {e.get("shortName") or ""} {e.get("posedBy") or ""} {(e.get("statement") or "")[:500]}'})
for f in json.load(open(f"{S}/openai_math_index.json"))["families"]:
    ext.append({"src": "openai", "id": f["family"], "name": f["title"], "resolution": "claimed", "text": f'{f["title"]} {f["summary"][:500]}'})
vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.3, sublinear_tf=True, stop_words="english")
X = vec.fit_transform(A + [e["text"] for e in ext]); XA, XE = X[:len(A)], X[len(A):]
sim = linear_kernel(XE, XA)
cands = []
for j, e in enumerate(ext):
    top = sim[j].argsort()[::-1][:3]
    for t in top:
        if sim[j, t] >= 0.25:
            i, f = keep[t]
            cands.append({"ext": e["src"], "ext_id": e["id"], "ext_name": e["name"], "ext_resolution": e["resolution"],
                          "lid": i, "paper": L[i]["paper"], "atlas_name": f[4], "atlas_status": f[2], "score": round(float(sim[j, t]), 3),
                          "atlas_text": " ".join(L[i]["text"].split())[:300], "ext_text": e["text"][:300]})
# exact: Erdős / Kourovka numbers
erd = re.compile(r"Erd(?:o|ő|\\H\{?o\}?)s(?:'s)?\s+(?:problem|question|conjecture)?\s*(?:#|no\.?|number)?\s*(\d{1,4})\b", re.I)
kour = re.compile(r"Kourovka\s*(\d{1,2}\.\d{1,3})", re.I)
exact = collections.defaultdict(list)
for i, f in keep:
    t = f[4] + " " + L[i]["text"]
    for m in erd.finditer(t): exact["erdos:" + m.group(1)].append(i)
    for m in kour.finditer(f[4]): exact["kourovka:" + m.group(1)].append(i)
json.dump({"tfidf": cands, "exact": exact}, open(f"{S}/atlas/ext_candidates.json", "w"), indent=0)
print(len(keep), "kept;", len(cands), "tfidf candidates (", collections.Counter(c["ext"] for c in cands), ");",
      len(exact), "exact keys", collections.Counter(k.split(":")[0] for k in exact))
