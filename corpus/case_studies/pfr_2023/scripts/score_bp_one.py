"""Run scripts/gold_candidates/score_bp_papers.one() for one blueprint on any paper graph.
usage: score_bp_one.py PAPER_JSON OUT_JSON [--bp corpus/gold_blueprints/teorth__pfr] [--arxiv 2311.05762] [--threshold 0.5]"""
import argparse, json, shutil, sys, tempfile
from pathlib import Path
REPO = Path("/mnt/c/Code/Github/Saranga")
sys.path.insert(0, str(REPO / "scripts/gold_candidates"))
import score_bp_papers as SB
ap = argparse.ArgumentParser()
ap.add_argument("paper"); ap.add_argument("out")
ap.add_argument("--bp", default=str(REPO / "corpus/gold_blueprints/teorth__pfr"))
ap.add_argument("--arxiv", default="2311.05762"); ap.add_argument("--threshold", type=float, default=0.5)
a = ap.parse_args()
bp = Path(a.bp).resolve()
d = Path(tempfile.mkdtemp()) / bp.name                 # a mirror of the blueprint dir: graph.json, paper/source, paper/full.json = ours
(d / "paper").mkdir(parents=True)
(d / "graph.json").symlink_to(bp / "graph.json")
(d / "paper/source").symlink_to(bp / "paper/source")
shutil.copy(a.paper, d / "paper/full.json")
_, out = SB.one(d, a.arxiv, a.threshold)
out["paper_graph"] = str(Path(a.paper).resolve())
Path(a.out).write_text(json.dumps(out, indent=1))
print(json.dumps({k: out[k] for k in ("blueprint_statements", "aligned", "aligned_by_number", "paper_results")}))
for p in ("author", "author_inv"):
    print(p, {k: round(v, 3) for k, v in out[p].items() if isinstance(v, (int, float)) and k.split("_")[0] in ("node", "edge")})
