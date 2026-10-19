#!/usr/bin/env python3
"""Per-paper time and token use of the v7 extraction run, from the agents' transcripts.

    python3 docs/v7_handoff/run_stats.py <subagents_dir> [--out docs/v7_handoff/run_stats_v7.tsv]

One row per extracted paper (the last agent that wrote its output JSON): set (silver or
gold-author), start and end (UTC), wall-clock minutes, tool calls, and tokens (output,
fresh input, cache read, cache write). Prints the mean and median per set.
"""
import argparse
import json
import re
import statistics as st
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IDLE = 600   # seconds: a gap between two consecutive transcript entries longer than this is not work
OUT = {"silver": REPO / "corpus/silver/opus-5.5__v7", "gold-author": REPO / "corpus/silver/opus-5.5__v7_gold",
       "gold-author-leaky": REPO / "corpus/silver/opus-5.5__v7_gold_leaky"}   # leaky: read the authors' diagram


def one(path):
    lines = path.read_text(errors="replace").splitlines()
    m = re.search(r"prompts_v7(nd)?/([^/\s]+?)\.md", lines[0]) if lines else None
    if not m:
        return None
    stamps, tools, tok = [], 0, dict(out=0, inp=0, cache_read=0, cache_write=0)
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("timestamp"):
            stamps.append(d["timestamp"])
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        u = msg.get("usage") or {}
        tok["out"] += u.get("output_tokens", 0)
        tok["inp"] += u.get("input_tokens", 0)
        tok["cache_read"] += u.get("cache_read_input_tokens", 0)
        tok["cache_write"] += u.get("cache_creation_input_tokens", 0)
        content = msg.get("content")
        if isinstance(content, list):
            tools += sum(1 for c in content if isinstance(c, dict) and c.get("type") == "tool_use")
    if len(stamps) < 2:
        return None
    ts = [datetime.fromisoformat(x.replace("Z", "+00:00")) for x in stamps]
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    active = sum(g for g in gaps if g <= IDLE)          # a longer gap is a stall (usage limit, disconnect)
    return dict(paper=m.group(2), stripped=bool(m.group(1)), start=stamps[0], end=stamps[-1], minutes=round(active / 60, 1),
                wall_minutes=round((ts[-1] - ts[0]).total_seconds() / 60, 1),
                stalled_minutes=round(sum(g for g in gaps if g > IDLE) / 60, 1), tool_calls=tools, **tok)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("subagents")
    ap.add_argument("--out", default=str(REPO / "docs/v7_handoff/run_stats_v7.tsv"))
    a = ap.parse_args()
    rows = {}
    for f in sorted(Path(a.subagents).glob("*.jsonl")):
        r = one(f)
        if not r:
            continue
        sets = ["gold-author"] if r["stripped"] else ["silver", "gold-author-leaky"]   # prompts_v7nd: diagram stripped
        r["set"] = next((s for s in sets if (OUT[s] / f"{r['paper']}.json").is_file()), None)
        key = (r["paper"], r["set"])
        if r["set"] and (key not in rows or r["end"] > rows[key]["end"]):
            rows[key] = r                              # a rerun replaces the earlier agent
    cols = ["paper", "set", "start", "end", "minutes", "wall_minutes", "stalled_minutes", "tool_calls", "out", "inp", "cache_read", "cache_write"]
    with open(a.out, "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in sorted(rows.values(), key=lambda r: r["start"]):
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")
    for s in OUT:
        x = [r for r in rows.values() if r["set"] == s]
        if x:
            print(f"{s}: {len(x)} papers, minutes mean {st.mean(r['minutes'] for r in x):.1f} median "
                  f"{st.median(r['minutes'] for r in x):.1f}; output tokens mean {st.mean(r['out'] for r in x):,.0f}; "
                  f"cache-read tokens mean {st.mean(r['cache_read'] for r in x):,.0f}")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
