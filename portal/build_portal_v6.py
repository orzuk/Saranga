#!/usr/bin/env python3
"""Point the portal at the v6 data.

  silver   Tier 2 = the 200 v6 silver papers (LLM pages <id>_new.html and
           rule-based pages <id>_rules.html, already built next to the JSON).
  tier3    Tier 3 = the 100K corpus: data/tier3_<version>/index.json (categories) and
           data/tier3_<version>/<cat>/index.json (one row per paper), built from the
           per-category corpus_stats.csv of a parse run; the manifest's tier3_index names
           it, and the pages and portal_server read the corpus from there. The main
           manifest no longer lists Tier-3 papers (too many for one file).

  cases    the paper's worked examples (manifest papers.tiercases), each graph and its viewer page in
           data/cases/, opened as paper.html?tier=cases&id=<id>: the v7 extractions of Candes-Tao and Donoho
           and the course graphs of Sinkhorn, VAE and GAN.

    python3 portal/build_portal_v6.py silver
    python3 portal/build_portal_v6.py cases
    python3 portal/build_portal_v6.py tier3 --stats <dir with <cat>/corpus_stats.csv> [--titles <csv>] [--version v7]
"""
import argparse
import csv
import json
import shutil
from pathlib import Path

PORTAL = Path(__file__).resolve().parent
REPO = PORTAL.parent
MANIFEST = PORTAL / "data" / "manifest.json"
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
    T3 = PORTAL / "data" / f"tier3_{args.version}"
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
    m["tier3_index"] = f"data/{T3.name}/index.json"
    save_manifest(m)
    print(f"tier3: {sum(c['count'] for c in cats)} papers in {len(cats)} categories")


CASES = {   # id -> (graph JSON, title); ARXIV: its arXiv id ("" when not on arXiv)
    "candes_tao_2005": ("corpus/silver/opus-5.5__v7_cases/candes_tao_2005.json", "Decoding by Linear Programming (Candes & Tao 2005)"),
    "donoho_2006": ("corpus/silver/opus-5.5__v7_cases/donoho_2006.json", "Compressed Sensing (Donoho 2006)"),
    "sinkhorn_2013": ("portal/data/tier2/paper005.json", "Sinkhorn Distances (Cuturi 2013)"),
    "vae_2014": ("portal/data/tier2/paper014.json", "Auto-Encoding Variational Bayes (Kingma & Welling 2014)"),
    "gan_2014": ("portal/data/tier2/paper015.json", "Generative Adversarial Nets (Goodfellow et al. 2014)"),
}


ARXIV = {"candes_tao_2005": "math/0502327", "donoho_2006": "", "sinkhorn_2013": "1306.0895",
         "vae_2014": "1312.6114", "gan_2014": "1406.2661"}


def cases(args):
    import subprocess
    import sys
    out = PORTAL / "data" / "cases"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for cid, (src, title) in CASES.items():
        d = json.load(open(REPO / src, encoding="utf-8"))
        d.setdefault("metadata", {})["title"] = title
        (out / f"{cid}.json").write_text(json.dumps(d), encoding="utf-8")
        subprocess.run([sys.executable, str(REPO / "src/graph_view/build.py"), str(out / f"{cid}.json"), "-o", str(out),
                        "--suffix", "_new", "--libs", "cdn"], check=True, capture_output=True)
        tc = {}
        for n in d.get("nodes", []):
            tc[n.get("type")] = tc.get(n.get("type"), 0) + 1
        rows.append({"paper_id": cid, "display_id": cid, "title": title,
                     "n_nodes": len(d.get("nodes", [])), "n_edges": len(d.get("edges", [])),
                     "type_counts": tc, "buckets": buckets(tc),
                     "top_node_types": sorted(tc.items(), key=lambda x: -x[1])[:6], "tier": "cases", "arxiv": ARXIV[cid],
                     "json_path": f"data/cases/{cid}.json", "graph_path": f"data/cases/{cid}_new.html"})
    m = load_manifest()
    m["papers"]["tiercases"] = rows
    save_manifest(m)
    print(f"cases: {len(rows)} worked examples in {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("silver"); a.add_argument("--silver", default="corpus/silver/opus-5.5__v6")
    b = sub.add_parser("tier3"); b.add_argument("--stats", required=True); b.add_argument("--titles")
    b.add_argument("--version", default="v7", help="the run: data/tier3_<version>/, and the bundles' <version>/")
    sub.add_parser("cases")
    args = ap.parse_args()
    {"silver": silver, "tier3": tier3, "cases": cases}[args.cmd](args)


if __name__ == "__main__":
    main()
