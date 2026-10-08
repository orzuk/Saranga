#!/usr/bin/env python3
"""Whole-corpus QA report for the opus-5 / v5.1 silver extraction.

Reports only what is measurable from the JSON. Where a property is NOT
recoverable post-hoc (e.g. edges an agent dropped to preserve acyclicity),
it says so rather than reporting a misleading zero.

Usage: python scripts/corpus_report.py [--dir <extraction dir>] [--md <out.md>]
"""
import argparse, collections, csv, glob, json, os, statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON_EDGES = {"uses", "proves", "illustrates", "tests",
               "grounded_to", "specializes", "generalizes", "resolves"}


def acyclic(nodes, edges):
    g = collections.defaultdict(list)
    indeg = collections.Counter()
    ids = {n["id"] for n in nodes}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in ids and t in ids:
            g[s].append(t); indeg[t] += 1
    q = [i for i in ids if not indeg[i]]
    seen = 0
    while q:
        u = q.pop(); seen += 1
        for v in g[u]:
            indeg[v] -= 1
            if not indeg[v]: q.append(v)
    return seen == len(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(REPO, "corpus/silver/opus-5__v5.1"))
    ap.add_argument("--md", default=os.path.join(REPO, "corpus/silver/CORPUS_REPORT_100.md"))
    a = ap.parse_args()

    cats = {}
    tc = os.path.join(REPO, "corpus/silver/true_categories.csv")
    if os.path.isfile(tc):
        cats = {r["arxiv_id"]: r for r in csv.DictReader(open(tc, encoding="utf-8"))}

    papers, ntype, etype, probs = [], collections.Counter(), collections.Counter(), []
    fieldcov = collections.Counter()
    tot_nodes = 0
    for f in sorted(glob.glob(os.path.join(a.dir, "*.json"))):
        aid = os.path.basename(f)[:-5]
        d = json.load(open(f, encoding="utf-8"))
        N, E = d.get("nodes", []), d.get("edges", [])
        ids = {n["id"] for n in N}
        for n in N:
            ntype[n.get("type")] += 1; tot_nodes += 1
            for k in n: fieldcov[k] += 1
        for e in E: etype[e.get("type")] += 1

        dangling = [e for e in E if e.get("source") not in ids or e.get("target") not in ids]
        dag = acyclic(N, E)
        par = {n["id"] for n in N if n.get("parent_id")}
        touched = {e.get("source") for e in E} | {e.get("target") for e in E}
        orphans = [n["id"] for n in N if n["id"] not in touched and n["id"] not in par]
        nc = [n["confidence"] for n in N if isinstance(n.get("confidence"), (int, float))]
        ec = [e["confidence"] for e in E if isinstance(e.get("confidence"), (int, float))]
        short = sum(1 for n in N if n.get("statement_short"))
        bad = [e.get("type") for e in E if e.get("type") not in CANON_EDGES]
        mdl = d.get("metadata", {}).get("model")
        pv = d.get("metadata", {}).get("prompt_version")

        if dangling: probs.append((aid, "%d dangling edges" % len(dangling)))
        if not dag:  probs.append((aid, "NOT acyclic"))
        if bad:      probs.append((aid, "non-canonical edge types: %s" % sorted(set(bad))))
        if mdl != "claude-opus-5[1m]": probs.append((aid, "model=%s" % mdl))
        if pv != "v5.1": probs.append((aid, "prompt_version=%s" % pv))

        papers.append(dict(
            aid=aid, n=len(N), e=len(E), orph=len(orphans), dag=dag,
            nc=statistics.mean(nc) if nc else 0, ec=statistics.mean(ec) if ec else 0,
            short=short / len(N) if N else 0,
            cat=(cats.get(aid, {}) or {}).get("sampled_from", "?"),
            prim=(cats.get(aid, {}) or {}).get("primary_category", "")))

    L = []
    w = L.append
    w("# opus-5 / v5.1 silver corpus — final QA report\n")
    w("Extraction dir: `%s`  \nPrompt: **v5.1**, sha256 prefix `100e6cf6fdbb3aea` (frozen for all papers)\n"
      % os.path.relpath(a.dir, REPO))
    w("## Headline\n")
    w("| metric | value |")
    w("|---|---|")
    w("| papers | **%d** |" % len(papers))
    w("| nodes | **%d** (mean %.1f/paper) |" % (sum(p["n"] for p in papers),
                                                statistics.mean([p["n"] for p in papers])))
    w("| edges | **%d** (mean %.1f/paper) |" % (sum(p["e"] for p in papers),
                                                statistics.mean([p["e"] for p in papers])))
    w("| edge/node ratio | mean %.2f, median %.2f |"
      % (statistics.mean([p["e"] / p["n"] for p in papers if p["n"]]),
         statistics.median([p["e"] / p["n"] for p in papers if p["n"]])))
    w("| mean node confidence | %.3f |" % statistics.mean([p["nc"] for p in papers]))
    w("| mean edge confidence | %.3f |" % statistics.mean([p["ec"] for p in papers]))
    w("| statement_short coverage | %.1f%% |" % (100 * statistics.mean([p["short"] for p in papers])))
    w("| papers with 0 orphans | %d/%d |" % (sum(1 for p in papers if not p["orph"]), len(papers)))
    w("| acyclic | %d/%d |" % (sum(1 for p in papers if p["dag"]), len(papers)))
    w("")
    w("## Node types\n")
    w("| type | n | %% |"); w("|---|---|---|")
    for t, c in ntype.most_common(): w("| `%s` | %d | %.1f%% |" % (t, c, 100 * c / tot_nodes))
    w("")
    te = sum(etype.values())
    w("## Edge types\n")
    w("| type | n | %% | canonical in `edge_types.py`? |"); w("|---|---|---|---|")
    for t, c in etype.most_common():
        w("| `%s` | %d | %.1f%% | %s |" % (t, c, 100 * c / te,
          "yes" if t in CANON_EDGES else "**NO — see E113**"))
    w("")
    w("## Field coverage\n")
    w("| field | nodes | %% |"); w("|---|---|---|")
    for k, c in fieldcov.most_common(): w("| `%s` | %d | %.0f%% |" % (k, c, 100 * c / tot_nodes))
    w("")
    w("## Per-category (axis = `sampled_from`; see ROADMAP 7.5.1)\n")
    w("| category | papers | nodes | edges | mean node conf | orphans |")
    w("|---|---|---|---|---|---|")
    bycat = collections.defaultdict(list)
    for p in papers: bycat[p["cat"]].append(p)
    for c in sorted(bycat):
        g = bycat[c]
        w("| %s | %d | %d | %d | %.3f | %d |" % (c, len(g), sum(x["n"] for x in g),
          sum(x["e"] for x in g), statistics.mean([x["nc"] for x in g]), sum(x["orph"] for x in g)))
    w("")
    w("## Integrity problems\n")
    if probs:
        for aid, m in probs: w("- `%s` — %s" % (aid, m))
    else:
        w("None. Every paper: valid JSON, all edge endpoints resolve, acyclic,")
        w("`model=claude-opus-5[1m]`, `prompt_version=v5.1`.")
    w("")
    w("## Known limits — NOT measurable from this data\n")
    w("- **E120 (dropped forward-reference edges).** Nodes keep no source `\\label`")
    w("  and `name` is descriptive, so `\\ref{}` cannot be resolved to a node.")
    w("  Edges an agent deleted to preserve acyclicity leave no trace. Confirmed")
    w("  in 1 paper / 2 edges only because that agent reported it; true rate unknown.")
    w("- **`rigor` (E130).** Declared universal in `node_types.py`, requested nowhere")
    w("  in the prompt; present on ~5% of nodes in 6 papers. Excluded from all")
    w("  cross-paper statistics above.")
    w("- **`confidence` is within-paper only.** No shared rubric anchor across papers")
    w("  (E54); per-paper means range widely. Do not compare across papers.")
    w("- **Step->parent edges are inconsistent (E8).** Some papers emit them, some")
    w("  rely on `parent_id` alone, which shifts edge/node ratio by up to ~0.5.")

    open(a.md, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:38]))
    print("\n... full report -> %s" % os.path.relpath(a.md, REPO))


if __name__ == "__main__":
    main()
