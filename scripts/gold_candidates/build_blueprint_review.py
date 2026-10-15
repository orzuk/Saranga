#!/usr/bin/env python3
"""Build the review material for Lean-blueprint gold candidates.

Reads the blueprint survey (blueprints.jsonl, judgments.json, repos/<owner>__<repo>/all.tex)
and writes, per blueprint, corpus/gold_blueprints/<owner>__<repo>/:
  graph.json, graph_new.html   the blueprint in our format (blueprint_to_graph.py) and its viewer page
  all.tex                      the blueprint's LaTeX
  paper/full.json, paper/full_new.html   our rule-based extraction of the matched arXiv paper (if any)
  meta.json                    what the review page shows
and corpus/gold_blueprints/index.json (all non-duplicate blueprints, with their provenance label).

Usage: build_blueprint_review.py <survey dir> [--ids owner/repo,...] [--no-paper]
"""
import argparse
import json
import random
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "corpus" / "gold_blueprints"
BUILD = REPO / "src" / "graph_view" / "build.py"
sys.path[:0] = [str(REPO / "portal"), str(Path(__file__).resolve().parent), str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
import blueprint_to_graph as b2g                       # noqa: E402
import yours                                           # noqa: E402


def url_ok(u: str) -> bool:
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "saranga-gold-review"})
        return urllib.request.urlopen(req, timeout=20).status == 200
    except Exception:                                  # noqa: BLE001
        return False


def web_links(rec: dict) -> dict:
    dg = rec.get("dep_graph_url") or ""
    out = {"repo": rec.get("repo_url"), "dep_graph": dg or None}
    if dg:
        base = dg.rsplit("/", 1)[0]                    # .../blueprint
        out["web"] = base + "/index.html"
        site = base.rsplit("/", 1)[0]
        for cand in (site + "/blueprint.pdf", base + "/blueprint.pdf"):
            if url_ok(cand):
                out["pdf"] = cand
                break
    return out


def our_paper(aid: str, d: Path) -> dict:
    """Our rule-based graph of the matched arXiv paper."""
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "full.json").is_file():
        src = d / "source"
        if not any(src.rglob("*.tex")) if src.exists() else True:
            yours.fetch_arxiv(aid, src)
            time.sleep(3)
        (d / "full.json").write_text(json.dumps(yours.parse_to_unified(yours.find_main_tex(src), aid, str(yours.RULES_DIR))))
    subprocess.run([sys.executable, str(BUILD), str(d / "full.json"), "-o", str(d), "--libs", "cdn"], capture_output=True, timeout=300)
    g = json.loads((d / "full.json").read_text())
    return {"page": "paper/full_new.html" if (d / "full_new.html").is_file() else None,
            "n_nodes": len(g.get("nodes", [])), "n_edges": len(g.get("edges", []))}


def build_one(rec: dict, judg: dict, survey: Path, do_paper: bool) -> dict:
    slug = rec["repo"].replace("/", "__")
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    tex = (survey / "repos" / slug / "all.tex").read_text(encoding="utf-8", errors="replace")
    (d / "all.tex").write_text(tex, encoding="utf-8")
    g = b2g.convert(tex, slug, rec.get("title") or rec["repo"])
    (d / "graph.json").write_text(json.dumps(g, indent=1))
    subprocess.run([sys.executable, str(BUILD), str(d / "graph.json"), "-o", str(d), "--libs", "cdn"], capture_output=True, timeout=600)
    ids = {n["id"]: n for n in g["nodes"]}
    st = [n for n in g["nodes"] if n["type"] != "proof"]
    uses = [e for e in g["edges"] if e["type"] == "uses"]
    rnd = random.Random(slug)
    sample = rnd.sample(uses, min(10, len(uses)))
    m = {"id": slug, "repo": rec["repo"], "title": rec.get("title") or rec["repo"],
         "provenance": rec.get("provenance_guess"), "area": (judg or {}).get("area") or rec.get("area"),
         "arxiv": (judg or {}).get("arxiv") if (judg or {}).get("matches_arxiv") else None,
         "arxiv_readme": rec.get("arxiv_candidates") or [], "coverage": (judg or {}).get("coverage") or rec.get("coverage"),
         "judgment_notes": (judg or {}).get("notes", ""), "stars": rec.get("stars"),
         "year": (rec.get("created_at") or "")[:4], "prov_signals": rec.get("prov_signals"),
         "n_statements": len(st), "n_proofs": len(g["nodes"]) - len(st), "n_uses": sum(e.get("kind") == "uses" for e in uses),
         "n_cited_only": sum(e.get("kind") == "ref" for e in uses),
         # every statement \uses (nearly) all earlier ones: no dependency information
         "degenerate": sum(e.get("kind") == "uses" for e in uses) > 20 * max(1, len(st)),
         "n_edges": len(g["edges"]), "types": {t: sum(n["type"] == t for n in st) for t in sorted({n["type"] for n in st})},
         "unresolved_uses": len(g["metadata"]["unresolved_uses"]),
         "n_leanok": sum("leanok" in n["tags"] for n in st),
         "page": "graph_new.html" if (d / "graph_new.html").is_file() else None,
         "links": web_links(rec),
         "source": {k[7:]: rec[k] for k in rec if k.startswith("source_") and rec[k]},   # the text it formalises
         "edge_sample": [{"source": e["source"], "target": e["target"],
                          "source_text": f"{ids[e['source']]['type']} {ids[e['source']].get('name') or ''}: {ids[e['source']]['statement'][:240]}",
                          "target_text": f"{ids[e['target']]['type']} {ids[e['target']].get('name') or ''}: {ids[e['target']]['statement'][:240]}"}
                         for e in sample]}
    if m["arxiv"] and do_paper:
        try:
            m["paper"] = our_paper(m["arxiv"], d / "paper")
        except Exception as e:                         # noqa: BLE001
            m["paper"] = {"error": repr(e)[:200]}
    (d / "meta.json").write_text(json.dumps(m, indent=1))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("survey")
    ap.add_argument("--ids", default="")
    ap.add_argument("--no-paper", action="store_true")
    a = ap.parse_args()
    survey = Path(a.survey)
    recs = [json.loads(l) for l in open(survey / "blueprints.jsonl")]
    judg = json.loads((survey / "judgments.json").read_text())
    recs = [dict(r, repo=r.get("repo") or r["id"]) for r in recs if not r.get("duplicate_of")]
    judg = {k: v for k, v in judg.items()}
    want = set(filter(None, a.ids.split(",")))
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for r in sorted(recs, key=lambda r: -r.get("stmt_with_uses", 0)):
        j = judg.get(r["repo"]) or {}
        row = {"id": r["repo"].replace("/", "__"), "repo": r["repo"], "title": r.get("title"),
               "provenance": j.get("provenance") or r.get("provenance_guess"), "area": j.get("area") or r.get("area"),
               "arxiv": j.get("arxiv") if j.get("matches_arxiv") else None,
               "statements": r.get("statements"), "stmt_with_uses": r.get("stmt_with_uses"),
               "uses_edges": r.get("uses_edges"), "year": (r.get("created_at") or "")[:4], "built": False,
               "source_type": r.get("source_type"), "source_latex": r.get("source_latex")}
        mf = OUT / row["id"] / "meta.json"
        if not want or r["repo"] in want:
            t0 = time.time()
            try:
                m = build_one(r, j, survey, not a.no_paper)
                row["built"] = bool(m.get("page"))
                print(f"{r['repo']:55s} {time.time() - t0:5.1f}s st={m['n_statements']} uses={m['n_uses']} "
                      f"arxiv={m['arxiv']} paper={bool((m.get('paper') or {}).get('page'))}", flush=True)
            except Exception as e:                     # noqa: BLE001
                print(f"{r['repo']:55s} ERROR {e!r}", flush=True)
        elif mf.is_file():
            row["built"] = bool(json.loads(mf.read_text()).get("page"))
        if mf.is_file():                                 # the counts of our (cleaned) conversion, not the survey's
            m = json.loads(mf.read_text())
            row |= {"statements": m["n_statements"], "stmt_with_uses": None, "uses_edges": m["n_uses"]}
        index.append(row)
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print("index:", len(index), "built:", sum(r["built"] for r in index))


if __name__ == "__main__":
    main()
