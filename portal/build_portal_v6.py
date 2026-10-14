#!/usr/bin/env python3
"""Point the portal at the v6 data.

  silver   Tier 2 = the 200 v6 silver papers (LLM pages <id>_new.html and
           rule-based pages <id>_rules.html, already built next to the JSON).
  tier3    Tier 3 = the 100K corpus: data/tier3_v6/index.json (categories) and
           data/tier3_v6/<cat>/index.json (one row per paper), built from the
           per-category corpus_stats.csv of a parse run. The main manifest no
           longer lists Tier-3 papers (too many for one file).

    python3 portal/build_portal_v6.py silver
    python3 portal/build_portal_v6.py tier3 --stats <dir with <cat>/corpus_stats.csv> [--titles <csv>]
"""
import argparse
import csv
import json
import shutil
from pathlib import Path

PORTAL = Path(__file__).resolve().parent
REPO = PORTAL.parent
MANIFEST = PORTAL / "data" / "manifest.json"
T3 = PORTAL / "data" / "tier3_v6"
BUCKETS = {
    "def": ["definition"],
    "thm": ["theorem", "lemma", "proposition", "corollary", "claim", "conjecture"],
    "alg": ["algorithm"],
    "pf": ["proof"],
    "steps": ["proof_step", "algorithm_step"],
    "other": ["equation", "problem", "open_problem", "assumption", "example", "remark"],
}


def buckets(tc):
    return {b: sum(tc.get(t, 0) for t in ts) for b, ts in BUCKETS.items()}


def load_manifest():
    return json.load(open(MANIFEST, encoding="utf-8"))


def save_manifest(m):
    if not (MANIFEST.parent / "manifest_before_v6.json").exists():
        shutil.copy(MANIFEST, MANIFEST.parent / "manifest_before_v6.json")
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


def silver(args):
    sdir = REPO / args.silver
    cats = {}
    split = REPO / "corpus/silver/split_v6_6-2-2.csv"
    if split.is_file():
        for r in csv.DictReader(open(split)):
            cats[r["arxiv_id"]] = (r["category"].replace("_", ".", 1).replace("math.ph", "math-ph"), r["split"])
    rows = []
    for f in sorted(sdir.glob("*.json")):
        d = json.load(open(f, encoding="utf-8"))
        tc = {}
        for n in d.get("nodes", []):
            tc[n.get("type")] = tc.get(n.get("type"), 0) + 1
        pid = f.stem
        cat, sp = cats.get(pid, ("", ""))
        rows.append({
            "paper_id": pid, "display_id": pid,
            "title": (d.get("metadata") or {}).get("title", ""),
            "category": cat, "split": sp,
            "n_nodes": len(d.get("nodes", [])), "n_edges": len(d.get("edges", [])),
            "type_counts": tc, "buckets": buckets(tc),
            "top_node_types": sorted(tc.items(), key=lambda x: -x[1])[:6],
            "tier": 2,
            "json_path": f"silver_v6/{pid}.json",
            "graph_path": f"silver_v6/graphs/{pid}_new.html",
            "graph_rules_path": f"silver_v6/graphs/{pid}_rules.html",
        })
    m = load_manifest()
    m["papers"]["tier2"] = rows
    save_manifest(m)
    print(f"tier2: {len(rows)} v6 silver papers")


def tier3(args):
    stats = Path(args.stats)
    titles = {}
    if args.titles:
        for r in csv.DictReader(open(args.titles, encoding="utf-8", errors="replace")):
            pid = r.get("id") or r.get("arxiv_id") or r.get("paper_id")
            if pid:
                titles[pid.split("v")[0] if "v" in pid else pid] = (r.get("title") or "").strip()
    T3.mkdir(parents=True, exist_ok=True)
    cats = []
    for cdir in sorted(p for p in stats.iterdir() if (p / "corpus_stats.csv").is_file()):
        cat = cdir.name
        rows = []
        for r in csv.DictReader(open(cdir / "corpus_stats.csv")):
            pid = r["paper_id"]
            g = lambda k: int(float(r.get(k) or 0))
            tc = {"definition": g("n_definitions"), "theorem": g("n_theorems"), "lemma": g("n_lemmas"),
                  "proposition": g("n_propositions"), "corollary": g("n_corollaries"), "claim": g("n_claims"),
                  "conjecture": g("n_conjectures"), "algorithm": g("n_algorithms"), "proof": g("n_proofs"),
                  "equation": g("n_equations"), "problem": g("n_problems"), "open_problem": g("n_open_problems"),
                  "assumption": g("n_assumptions"), "example": g("n_examples"), "remark": g("n_remarks")}
            rows.append({"paper_id": pid, "title": titles.get(pid.split("v")[0], ""),
                         "n_nodes": g("n_nodes"), "n_edges": g("n_edges"), "buckets": buckets(tc),
                         "acyclic": r.get("dag_acyclic") == "True", "tier": 3, "category": cat,
                         "json_path": f"t3json?cat={cat}&id={pid}_rules",
                         "graph_path": f"render3?cat={cat}&id={pid}_rules"})
        (T3 / cat).mkdir(exist_ok=True)
        (T3 / cat / "index.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        cats.append({"category": cat, "count": len(rows),
                     "avg_nodes": round(sum(x["n_nodes"] for x in rows) / max(1, len(rows)), 1)})
    (T3 / "index.json").write_text(json.dumps({"source": str(stats), "categories": cats}, indent=1), encoding="utf-8")
    m = load_manifest()
    m["papers"]["tier3"] = []
    m["tier3_index"] = "data/tier3_v6/index.json"
    save_manifest(m)
    print(f"tier3: {sum(c['count'] for c in cats)} papers in {len(cats)} categories")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("silver"); a.add_argument("--silver", default="corpus/silver/opus-5.5__v6")
    b = sub.add_parser("tier3"); b.add_argument("--stats", required=True); b.add_argument("--titles")
    args = ap.parse_args()
    {"silver": silver, "tier3": tier3}[args.cmd](args)


if __name__ == "__main__":
    main()
