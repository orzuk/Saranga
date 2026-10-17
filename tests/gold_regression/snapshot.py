#!/usr/bin/env python3
"""Regression snapshot of the author-diagram conversion (LaTeX -> parsed drawings -> gold graph).

Runs the conversion of every paper in corpus/gold_candidates/papers on a mirror of the folders
(inputs linked read-only, outputs written to the mirror; the rule-based extraction full.json is
reused, the viewer pages are not built), and writes one JSON per paper: the parsed drawings, the gold
graph and the review rows. Two snapshots are compared with --diff.

    snapshot.py OUT_DIR [--ids a,b] [--jobs 6]
    snapshot.py --diff OLD_DIR NEW_DIR
"""
import argparse, json, os, shutil, sys, tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPERS = REPO / "corpus" / "gold_candidates" / "papers"
INPUTS = ("paper.tex", "figure.json", "sty", "src")


def one(job):
    pid, out_dir, mirror_root = job
    sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src"), str(REPO / "scripts" / "gold_candidates")]
    import build_gold_review as B
    import subprocess
    src, m = PAPERS / pid, Path(mirror_root) / pid
    m.mkdir(parents=True, exist_ok=True)
    for name in INPUTS:
        if (src / name).exists() and not (m / name).exists():
            os.symlink(src / name, m / name)
    for name in ("graph_tikz.json",):                    # the survey's own parse is the fallback: a copy, not a link
        if (src / name).is_file():
            shutil.copyfile(src / name, m / name)
    full = json.loads((src / "full.json").read_text()) if (src / "full.json").is_file() else {"nodes": [], "metadata": {}}
    B.parse_to_unified = lambda *a, **k: full
    B.subprocess = type("NoPages", (), {"run": staticmethod(lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))})
    try:
        meta = B.build_one(m, False)
    except Exception as e:                               # noqa: BLE001
        meta = {"error": repr(e)}
    rec = {"meta": {k: v for k, v in meta.items() if k not in ("gold_page", "full_page")}}
    for name in ("graph_tikz.json", "gold.json"):
        f = m / name
        rec[name] = json.loads(f.read_text()) if f.is_file() else None
    Path(out_dir, pid + ".json").write_text(json.dumps(rec, indent=0, sort_keys=True, ensure_ascii=False))
    return pid


def diff(a, b):
    a, b = Path(a), Path(b)
    names = sorted({p.name for p in a.glob("*.json")} | {p.name for p in b.glob("*.json")})
    bad = []
    for n in names:
        x = json.loads((a / n).read_text()) if (a / n).is_file() else None
        y = json.loads((b / n).read_text()) if (b / n).is_file() else None
        if x != y:
            parts = [k for k in ("meta", "graph_tikz.json", "gold.json") if (x or {}).get(k) != (y or {}).get(k)]
            bad.append((n[:-5], parts))
    print(f"{len(names)} papers, {len(bad)} differ")
    for pid, parts in bad[:50]:
        print(" ", pid, parts)
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--ids", default="")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--diff", nargs=2)
    a = ap.parse_args()
    if a.diff:
        sys.exit(0 if diff(*a.diff) else 1)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ids = a.ids.split(",") if a.ids else sorted(p.name for p in PAPERS.iterdir() if p.is_dir())
    mirror = tempfile.mkdtemp(prefix="gold_mirror_")
    with ProcessPoolExecutor(a.jobs) as pool:
        for k, _ in enumerate(pool.map(one, [(i, str(out), mirror) for i in ids]), 1):
            if k % 100 == 0:
                print(k, flush=True)
    shutil.rmtree(mirror, ignore_errors=True)
    print(len(ids), "papers ->", out)


if __name__ == "__main__":
    main()
