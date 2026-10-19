#!/usr/bin/env python3
"""Corpus statistics, time and cost of an LLM silver run: the figures of the paper's silver table.

    python3 docs/v7_handoff/silver_stats.py corpus/silver/opus-5.5__v7 [--transcripts <subagents_dir>]
        [--tex-dir corpus/silver/tex_pool] [--out docs/v7_handoff/silver_stats_v7.json]

Same definitions as docs/v6_silver_report.md: results = theorem, lemma, proposition, corollary, claim,
conjecture; steps = proof_step + algorithm_step; a proof is decomposed when a step has it as parent;
finishing-step errors and warnings from finalize() re-run on a copy of each output. With --transcripts
(the run's agent transcripts, matched to papers by the prompt path in their first line; the last agent
per paper counts): active minutes (gaps over 10 min are stalls, as in run_stats.py), model calls,
tokens processed (input + cache read + cache write), generated tokens (characters the model wrote / 3.5,
since streamed calls under-record output tokens) and the cost at the v6 report's assumed list prices.
"""
import argparse
import copy
import json
import re
import statistics as st
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src")]
RESULTS = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
STEPS = {"proof_step", "algorithm_step"}
PRICE = {"inp": 5, "out": 25, "cache_read": 0.5, "cache_write": 6.25}   # $ per M tokens (v6 report)
IDLE = 600


def q(xs):
    """median [lower quartile - upper quartile]"""
    xs = sorted(xs)
    qs = st.quantiles(xs, n=4) if len(xs) > 1 else [xs[0]] * 3
    return {"median": st.median(xs), "q1": qs[0], "q3": qs[2], "mean": st.mean(xs), "min": xs[0], "max": xs[-1]}


def corpus(d, tex_dir):
    from extraction_finalize import finalize
    from latex_facts import read_tex
    per, tot = [], Counter()
    types, etypes, notes, rigor = Counter(), Counter(), Counter(), Counter()
    for f in sorted(Path(d).glob("*.json")):
        g = json.loads(f.read_text())
        nodes, edges = g["nodes"], g["edges"]
        t = Counter(n["type"] for n in nodes)
        types.update(t)
        etypes.update(e.get("type", "uses") for e in edges)
        l1 = [n for n in nodes if n["type"] not in STEPS]
        proofs = {n["id"] for n in nodes if n["type"] == "proof"}
        decomposed = {n.get("parent_id") for n in nodes if n["type"] == "proof_step"} & proofs
        rigor.update(n["rigor"] for n in nodes if n.get("rigor") and n["rigor"] != "formal")
        notes.update(x.get("category", "?") for x in g["metadata"].get("extraction_notes") or [])
        rep = finalize(copy.deepcopy(g), read_tex(str(Path(tex_dir) / f"{f.stem}.tex")))
        row = dict(paper=f.stem, nodes=len(nodes), level1=len(l1), steps=sum(t[x] for x in STEPS),
                   results=sum(t[x] for x in RESULTS), equations=t["equation"], edges=len(edges),
                   external=sum(n.get("origin") == "external" for n in l1), proofs=len(proofs),
                   decomposed=len(decomposed), errors=len(rep["errors"]), warnings=len(rep["warnings"]),
                   notes=len(g["metadata"].get("extraction_notes") or []))
        per.append(row)
        tot.update({k: v for k, v in row.items() if k != "paper"})
    return per, tot, types, etypes, notes, rigor


def transcript(path):
    lines = path.read_text(errors="replace").splitlines()
    m = re.search(r"prompts_v7[a-z]*/([^/\s]+?)\.md", lines[0]) if lines else None
    if not m:
        return None
    stamps, seen, tok = [], set(), Counter()
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("timestamp"):
            stamps.append(datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")))
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        if msg.get("role") != "assistant":
            continue
        u, mid = msg.get("usage") or {}, msg.get("id")
        if mid not in seen:                                  # one model call may span several entries
            seen.add(mid)
            tok["inp"] += u.get("input_tokens", 0)
            tok["cache_read"] += u.get("cache_read_input_tokens", 0)
            tok["cache_write"] += u.get("cache_creation_input_tokens", 0)
        for c in msg.get("content") or []:
            if isinstance(c, dict):
                tok["chars"] += len(c.get("text") or c.get("thinking") or "") + (
                    len(json.dumps(c.get("input"))) if c.get("type") == "tool_use" else 0)
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
    out = tok["chars"] / 3.5
    cost = (tok["inp"] * PRICE["inp"] + out * PRICE["out"] + tok["cache_read"] * PRICE["cache_read"]
            + tok["cache_write"] * PRICE["cache_write"]) / 1e6
    return dict(paper=m.group(1), end=stamps[-1] if stamps else None, calls=len(seen),
                minutes=sum(g for g in gaps if g <= IDLE) / 60,
                processed=tok["inp"] + tok["cache_read"] + tok["cache_write"], generated=out, cost=cost)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("silver")
    ap.add_argument("--transcripts")
    ap.add_argument("--tex-dir", default=str(REPO / "corpus/silver/tex_pool"))
    ap.add_argument("--out")
    a = ap.parse_args()
    per, tot, types, etypes, notes, rigor = corpus(a.silver, a.tex_dir)
    papers = {r["paper"] for r in per}
    res = {"papers": len(per), "totals": dict(tot), "node_types": dict(types), "edge_types": dict(etypes),
           "notes": dict(notes), "rigor_nonformal": dict(rigor),
           "per_paper": {k: q([r[k] for r in per]) for k in per[0] if k != "paper"},
           "external_share": tot["external"] / tot["level1"], "decomposed_share": tot["decomposed"] / tot["proofs"],
           "papers_without_warnings": sum(r["warnings"] == 0 for r in per)}
    if a.transcripts:
        runs = {}
        for f in Path(a.transcripts).glob("*.jsonl"):
            r = transcript(f)
            if r and r["paper"] in papers and r["end"] and (r["paper"] not in runs or r["end"] > runs[r["paper"]]["end"]):
                runs[r["paper"]] = r
        rs = list(runs.values())
        res["run"] = {"papers": len(rs), **{k: {"total": sum(r[k] for r in rs), **q([r[k] for r in rs])}
                                            for k in ("minutes", "calls", "processed", "generated", "cost")}}
    print(json.dumps({k: v for k, v in res.items() if k != "per_paper"}, indent=1, default=str))
    for k, v in res["per_paper"].items():
        print(f"  {k:10s} median {v['median']:g} [{v['q1']:g}-{v['q3']:g}]  mean {v['mean']:.1f}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
