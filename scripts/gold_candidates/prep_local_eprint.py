#!/usr/bin/env python3
"""Prepare a gold-candidate folder from a locally cached arXiv e-print (papers the cluster copy lacks).

Usage: prep_local_eprint.py <paper id> <e-print file> <scan.jsonl> <fetch_eprints.py>
Writes papers/<id>/{src/, paper.tex, figure.json, graph_tikz.json} with the cluster agent's
figure locator and diagram parsers (fetch_eprints.py), so the result matches the cluster folders.
"""
import importlib.util, json, shutil, sys
from pathlib import Path

pid, ep, scan, fe = sys.argv[1:5]
REPO = Path(__file__).resolve().parents[2]
d = REPO / "corpus" / "gold_candidates" / "papers" / pid
d.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("fe", fe); F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
raw = Path(ep).read_bytes()
import gzip, tarfile, io
data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
sd = d / "src"; sd.mkdir(exist_ok=True)
try:
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile() and not m.name.startswith("/") and ".." not in m.name:
                tf.extract(m, sd)
except tarfile.TarError:
    (sd / "main.tex").write_bytes(data)
for f in list(sd.rglob("*")):                      # old e-prints: LaTeX files without an extension
    if f.is_file() and not f.suffix and f.stat().st_size < 5_000_000:
        head = f.read_bytes()[:4000]
        if b"\\" in head and not f.with_suffix(".tex").exists():
            shutil.copy(f, f.with_suffix(".tex"))
recs = []
for line in open(scan):
    r = json.loads(line)
    if r["id"] == pid:
        recs = [{"caption": f.get("caption", ""), "src_snip": f.get("ctx", "")[-200:]} for f in r["figs"] if f.get("strong") or f.get("hit_cap")] or [{"caption": f.get("caption", ""), "src_snip": ""} for f in r["figs"]]
        break
figs, lmap, macros = F.locate_figures(str(sd), recs)
for k, f in enumerate(figs):
    f["fig_idx"] = k
graphs = []
for f in figs:
    if not f.get("found"):
        continue
    for code in f.get("tikz", []):
        g = F.parse_tikz(code, lmap, macros); g["fig_idx"] = f["fig_idx"]; g["format"] = "tikz"; graphs.append(g)
    for code in f.get("xymatrix", []):
        g = F.parse_grid(code, "xymatrix", lmap, macros); g["fig_idx"] = f["fig_idx"]; g["format"] = "xymatrix"; graphs.append(g)
    for code in f.get("picture", []):
        g = F.parse_picture(code, lmap, macros); g["fig_idx"] = f["fig_idx"]; g["format"] = "picture"; graphs.append(g)
json.dump({"id": pid, "status": "ok", "figures": figs}, open(d / "figure.json", "w"), indent=1, ensure_ascii=False)
if graphs:
    json.dump(graphs, open(d / "graph_tikz.json", "w"), indent=1, ensure_ascii=False)
# one flattened LaTeX file for our parser: the main file with \input/\include inlined
sys.path[:0] = [str(REPO / "portal")]
import yours
main = yours.find_main_tex(sd)
import latex_facts
(d / "paper.tex").write_text(latex_facts.read_tex(str(main), sd), encoding="utf-8")
print(pid, "figures found:", sum(1 for f in figs if f.get("found")), "graphs:", [(g["format"], len(g["nodes"]), len(g["edges"])) for g in graphs])
