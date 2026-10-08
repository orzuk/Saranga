#!/usr/bin/env python3
"""Compare the v6 pilot's model arms: cost, speed, richness, validity, agreement.

    python3 scripts/compare_pilot_arms.py [--pilot corpus/silver/pilot_v6]

Per arm, over the papers every arm finished:
  - wall time, turns, output and thinking tokens, list cost (from the CLI logs)
  - nodes and edges by type; nodes matched to environment facts vs found in prose
  - post-pass health: errors/warnings when re-running extraction_finalize
  - agreement: share of an arm's prose nodes whose span another arm also found,
    and overlap with the v5.1 silver extraction of the same paper
"""
import argparse, collections, glob, json, os, re, statistics, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
import latex_facts as LF                     # noqa: E402
import extraction_finalize as XF             # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pilot", default=os.path.join(REPO, "corpus/silver/pilot_v6"))
a = ap.parse_args()

ARMS = [d for d in sorted(os.listdir(a.pilot))
        if os.path.isdir(os.path.join(a.pilot, d)) and not d.startswith("_")]
done = {arm: {os.path.basename(f)[:-5] for f in glob.glob(f"{a.pilot}/{arm}/*.json")} for arm in ARMS}
papers = sorted(set.intersection(*done.values())) if done else []
LEVEL2 = {"proof_step", "algorithm_step"}


def key(s):
    return re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", s or ""))[:120]


def run_log(arm, pid):
    try:
        return json.load(open(f"{a.pilot}/_runs/{arm}__{pid}.json"))
    except Exception:
        return {}


tex = {p: open(f"{REPO}/corpus/silver/tex_pool/{p}.tex", errors="replace").read() for p in papers}
facts = {p: LF.extract_facts(tex[p]) for p in papers}
graphs = {arm: {p: json.load(open(f"{a.pilot}/{arm}/{p}.json")) for p in papers} for arm in ARMS}
v51 = {}
for p in papers:
    f = f"{REPO}/corpus/silver/opus-5__v5.1/{p}.json"
    if os.path.exists(f):
        v51[p] = json.load(open(f))

prose_keys = {arm: {} for arm in ARMS}
rows = {}
for arm in ARMS:
    r = collections.Counter()
    times, turns, outs, thinks, costs = [], [], [], [], []
    types = collections.Counter()
    for p in papers:
        log = run_log(arm, p)
        u = log.get("usage", {})
        times.append(log.get("duration_ms", 0) / 60000)
        turns.append(log.get("num_turns", 0))
        outs.append(u.get("output_tokens", 0))
        thinks.append((u.get("output_tokens_details") or {}).get("thinking_tokens", 0))
        costs.append(log.get("total_cost_usd", 0) or 0)
        g = graphs[arm][p]
        n2f = XF.match_nodes_to_facts(g, facts[p])
        lvl1 = [n for n in g["nodes"] if n.get("type") not in LEVEL2]
        r["nodes"] += len(g["nodes"]); r["edges"] += len(g["edges"])
        r["level1"] += len(lvl1); r["from_env"] += len(n2f)
        r["steps"] += sum(n.get("type") == "proof_step" for n in g["nodes"])
        r["backward"] += sum(bool(e.get("backward")) for e in g["edges"])
        for n in lvl1:
            types[n["type"]] += 1
        prose_keys[arm][p] = {key(n.get("statement")) for n in lvl1 if n["id"] not in n2f}
        # re-run the post-pass on a copy: does the finished graph still pass?
        rep = XF.finalize(json.loads(json.dumps(g)), tex[p])
        r["errors"] += len(rep["errors"]); r["warnings"] += len(rep["warnings"])
        r["papers_with_errors"] += bool(rep["errors"])
    r["prose"] = r["level1"] - r["from_env"]
    rows[arm] = dict(r, minutes=statistics.median(times) if times else 0,
                     minutes_total=sum(times), turns=statistics.median(turns) if turns else 0,
                     out_tok=statistics.median(outs) if outs else 0,
                     think_tok=statistics.median(thinks) if thinks else 0,
                     cost=sum(costs), types=types)

# agreement: a prose node "confirmed" if some other arm found the same span
for arm in ARMS:
    conf = tot = v = vt = 0
    for p in papers:
        mine = prose_keys[arm][p]
        others = set().union(*(prose_keys[o][p] for o in ARMS if o != arm))
        conf += len(mine & others); tot += len(mine)
        if p in v51:
            ref = {key(n.get("statement")) for n in v51[p]["nodes"] if n.get("type") not in LEVEL2}
            v += len(mine & ref); vt += len(mine)
    rows[arm]["prose_confirmed"] = conf / tot if tot else 0
    rows[arm]["prose_in_v51"] = v / vt if vt else 0

print(f"papers finished by every arm: {len(papers)}  ({', '.join(papers)})\n")
cols = [("median min/paper", "minutes", "{:.1f}"), ("median turns", "turns", "{:.0f}"),
        ("median output tok", "out_tok", "{:,.0f}"), ("median thinking tok", "think_tok", "{:,.0f}"),
        ("list cost, all papers $", "cost", "{:.2f}"), ("nodes", "nodes", "{}"), ("edges", "edges", "{}"),
        ("level-1 nodes", "level1", "{}"), ("  from environments", "from_env", "{}"),
        ("  found in prose", "prose", "{}"), ("proof steps", "steps", "{}"),
        ("backward edges", "backward", "{}"), ("post-pass errors", "errors", "{}"),
        ("post-pass warnings", "warnings", "{}"),
        ("prose nodes also found by another arm", "prose_confirmed", "{:.0%}"),
        ("prose nodes also in v5.1 silver", "prose_in_v51", "{:.0%}")]
print(f"{'':40s}" + "".join(f"{arm:>16s}" for arm in ARMS))
for label, k, fmt in cols:
    print(f"{label:40s}" + "".join(f"{fmt.format(rows[arm][k]):>16s}" for arm in ARMS))
print()
alltypes = sorted(set().union(*(rows[arm]["types"] for arm in ARMS)))
for t in alltypes:
    print(f"  {t:38s}" + "".join(f"{rows[arm]['types'][t]:>16d}" for arm in ARMS))
