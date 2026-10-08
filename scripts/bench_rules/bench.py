#!/usr/bin/env python3
"""Benchmark the rule-based extractor, and check its speed-ups changed nothing.

    python3 scripts/bench_rules/bench.py --mode reference --out OUT/ref  P1 P2 ...
    python3 scripts/bench_rules/bench.py --mode fast      --out OUT/fast P1 P2 ...
    python3 scripts/bench_rules/bench.py --compare OUT/ref OUT/fast

`fast` is the extractor as it runs everywhere. `reference` sets
SARANGA_REGEX_REFERENCE=1, which turns the speed-ups in rule_guard.py and the
parser's rule-module cache off: the plain path, kept only for this check. Run
it whenever the rules change (a new rule set could, in principle, break an
assumption a speed-up relies on). Each mode runs in its own process on a fresh
copy of the extractor (the timeout guard may comment rules out at source, so
the tracked files are never used directly). Output per paper: the unified
JSON, sorted, so a byte comparison is an exact check.
"""
import argparse, contextlib, io, json, os, shutil, sys, time, filecmp, statistics

REPO = os.environ.get("SARANGA_BENCH_REPO", "/mnt/c/Code/Github/Saranga")
EXT = f"{REPO}/extractors/rules/silver_v5.1__subset_selection__2026-08"
TEX = f"{REPO}/corpus/silver/tex_pool"

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["reference", "fast"])
ap.add_argument("--out")
ap.add_argument("--compare", nargs=2)
ap.add_argument("--tex-dir", help="directory of <paper>.tex (default: corpus/silver/tex_pool)")
ap.add_argument("papers", nargs="*")
a = ap.parse_args()

if a.compare:
    A, B = a.compare
    ta, tb = (json.load(open(f"{d}/_times.json")) for d in (A, B))
    same = [p for p in ta if filecmp.cmp(f"{A}/{p}.json", f"{B}/{p}.json", shallow=False)]
    print(f"{'paper':14s} {'base s':>7s} {'fast s':>7s} {'speedup':>7s} identical")
    for p in ta:
        print(f"{p:14s} {ta[p]:7.2f} {tb[p]:7.2f} {ta[p]/tb[p]:6.1f}x  {'yes' if p in same else 'NO'}")
    print(f"{'TOTAL':14s} {sum(ta.values()):7.2f} {sum(tb.values()):7.2f} "
          f"{sum(ta.values())/sum(tb.values()):6.1f}x  {len(same)}/{len(ta)} identical")
    sys.exit(0 if len(same) == len(ta) else 1)

os.makedirs(a.out, exist_ok=True)
ext = a.out + "/_extractor"
shutil.rmtree(ext, ignore_errors=True)
shutil.copytree(EXT, ext)
sys.path[:0] = [f"{REPO}/src/LLMVersion", f"{REPO}/src"]
if a.mode == "reference":
    os.environ["SARANGA_REGEX_REFERENCE"] = "1"    # read when rule_guard is imported
from math_paper_parser import PaperParser

parser = PaperParser(extraction_mode="rules", rules_dir=ext)
times = {}
texdir = a.tex_dir or TEX
for pid in a.papers:
    t = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        g = parser.parse_file(f"{texdir}/{pid}.tex")
    times[pid] = time.perf_counter() - t
    d = g.to_unified_dict(include_research_fields=True)
    d.get("metadata", {}).pop("extraction_date", None)
    with open(f"{a.out}/{pid}.json", "w") as f:
        json.dump(d, f, sort_keys=True, ensure_ascii=False, indent=0)
    print(f"{pid}: {times[pid]:.2f}s", flush=True)
json.dump(times, open(f"{a.out}/_times.json", "w"), indent=1)
