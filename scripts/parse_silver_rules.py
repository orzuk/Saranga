#!/usr/bin/env python3
"""Rule-based graphs for the silver papers, next to the LLM ones.

Parses every paper of the silver corpus with a rule set and writes
<silver>/<out>/<id>.json (default rules_v6; the paper's title and metadata copied from the
silver JSON); then build its viewer pages as <silver>/graphs/<id>_rules.html:

    python3 scripts/parse_silver_rules.py [--rules-dir ...] [--workers 6]
    python3 src/graph_view/build.py corpus/silver/opus-5.5__v6/rules_v6/*.json \\
        -o corpus/silver/opus-5.5__v6/graphs --suffix _rules
"""
import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src"), str(REPO / "scripts")]


def one(job):
    pid, silver, tex, rules, out, name = job
    from math_paper_parser import parse_to_unified
    from latex_facts import find_main_tex
    main = find_main_tex(Path(tex) / pid / "source")
    if not main:
        return pid, "no tex"
    try:
        d = parse_to_unified(main, pid, rules)
        meta = json.load(open(Path(silver) / f"{pid}.json")).get("metadata", {})
        d["metadata"] = {**meta, **{k: v for k, v in d.get("metadata", {}).items() if v}}
        d["metadata"]["extractor"] = name
        json.dump(d, open(Path(out) / f"{pid}.json", "w"), ensure_ascii=False)
        return pid, "ok"
    except Exception as e:                                   # noqa: BLE001
        return pid, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--silver", default="corpus/silver/opus-5.5__v6")
    ap.add_argument("--tex", default="corpus/silver/tex_staged")
    ap.add_argument("--rules-dir", default="extractors/rules/silver_v6__sentence_rules_haiku__2026-10")
    ap.add_argument("--out", default="rules_v6", help="output folder inside --silver")
    ap.add_argument("--name", default=None, help="extractor name in the metadata (default: the rules dir name)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    silver = REPO / a.silver
    out = silver / a.out
    out.mkdir(exist_ok=True)
    pids = sorted(p.stem for p in silver.glob("*.json"))
    rules = (REPO / a.rules_dir).resolve()
    jobs = [(p, str(silver), str(REPO / a.tex), str(rules), str(out), a.name or rules.name) for p in pids]
    with mp.Pool(a.workers) as pool:
        res = pool.map(one, jobs)
    bad = [r for r in res if r[1] != "ok"]
    print(f"{len(res) - len(bad)}/{len(res)} parsed into {out}")
    for pid, msg in bad:
        print("  ", pid, msg)


if __name__ == "__main__":
    main()
